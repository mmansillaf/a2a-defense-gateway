import hashlib
import json
import logging
import os
import sqlite3
import time
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("a2a.financial_policy")


class PolicyConfig(BaseModel):
    """Configuración determinista del Policy Proxy para gasto agéntico M2M."""
    model_config = ConfigDict(extra="forbid")

    max_per_tx_usd: float = Field(default=0.25, gt=0)
    max_per_hour_usd: float = Field(default=2.00, gt=0)
    max_per_day_usd: float = Field(default=10.00, gt=0)
    hitl_threshold_usd: float = Field(default=1.00, gt=0)
    max_consecutive_errors: int = Field(default=3, gt=0)
    allowlist_domains: list[str] = Field(
        default_factory=lambda: [
            "127.0.0.1",
            "localhost",
            "a2a.vilmamonroy.com",
            "api.moltbook.com",
            "api.proveedor-verificado.com",
            "courtlistener.com",
            "www.courtlistener.com",
            "sec.gov",
            "www.sec.gov",
        ]
    )


class ProxyPaymentIntent(BaseModel):
    """Intención de pago o consumo M2M emitida por un agente."""
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    target_url: str
    amount_usd: float = Field(..., ge=0.0)
    method: str = "POST"
    payload: dict = Field(default_factory=dict)
    challenge_headers: dict[str, str] = Field(default_factory=dict)


class PolicyEvaluationResult(BaseModel):
    """Veredicto determinista de la evaluación de políticas de pago."""
    model_config = ConfigDict(extra="forbid")

    decision: str  # ALLOWED, BLOCKED, PENDING_HITL, ERROR
    status_code: int
    reason: str
    domain: str
    agent_id: str
    amount_usd: float
    circuit_tripped: bool = False
    spent_hour_usd: float = 0.0
    spent_day_usd: float = 0.0


class SagaStep(BaseModel):
    """Paso unitario dentro de una transacción M2M orquestada mediante Saga."""
    model_config = ConfigDict(extra="forbid")

    step_id: str
    agent_id: str
    service_name: str
    action_type: str  # EXECUTE, COMPENSATE
    payload: dict = Field(default_factory=dict)
    compensation_payload: dict = Field(default_factory=dict)
    cost_usd: float = 0.0


class SagaExecutionResult(BaseModel):
    """Resultado de ejecución de una Saga M2M con compensaciones automáticas."""
    model_config = ConfigDict(extra="forbid")

    saga_id: str
    status: str  # COMPLETED, COMPENSATED, FAILED
    steps_executed: int
    steps_compensated: int
    total_cost_usd: float
    execution_trail: list[dict]
    error_detail: str | None = None


class FinancialPolicyProxy:
    """
    Motor de gobernanza financiera M2M y cortafuegos de pagos agénticos.
    Implementa controles contra inyecciones de prompt financieras (FIN-01),
    circuit breakers ante bucles de fallo post-pago (FIN-02),
    control de velocidad presupuestaria horaria/diaria (FIN-03),
    mitigación de inflación súbita de precios con HITL (FIN-04),
    y validación estricta de retos HTTP 402 (FIN-05).
    """

    def __init__(
        self,
        config: PolicyConfig | None = None,
        db_path: str | None = None,
    ):
        self.config = config or PolicyConfig()
        self.db_path = db_path or os.getenv("A2A_PAYMENT_AUDIT_DB", "data/payment_audit.db")
        self._init_db()

    def _init_db(self) -> None:
        if self.db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    agent_id TEXT NOT NULL,
                    target_url TEXT NOT NULL,
                    amount_usd REAL NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT,
                    tx_hash TEXT,
                    payload_hash TEXT
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS circuit_state (
                    domain TEXT PRIMARY KEY,
                    consecutive_errors INTEGER DEFAULT 0,
                    tripped INTEGER DEFAULT 0,
                    last_failure_timestamp REAL
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS saga_records (
                    saga_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    steps_count INTEGER NOT NULL,
                    trail_json TEXT NOT NULL
                );
            """)

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def log_event(
        self,
        agent_id: str,
        target_url: str,
        amount_usd: float,
        status: str,
        reason: str = "",
        tx_hash: str = "",
        payload_hash: str = "",
    ) -> None:
        """Registra un evento transaccional en la bitácora auditable de SQLite."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_log (
                    timestamp, agent_id, target_url, amount_usd, status, reason, tx_hash, payload_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (time.time(), agent_id, target_url, amount_usd, status, reason, tx_hash, payload_hash),
            )

    def get_spent(self, agent_id: str, window_seconds: int) -> float:
        """Calcula el gasto total acumulado por un agente dentro de una ventana temporal."""
        cutoff = time.time() - window_seconds
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(amount_usd), 0.0)
                FROM audit_log
                WHERE agent_id = ? AND status = 'PAID_SUCCESS' AND timestamp >= ?;
                """,
                (agent_id, cutoff),
            ).fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0

    def check_and_update_circuit(
        self,
        domain: str,
        is_error: bool = False,
        reset: bool = False,
    ) -> bool:
        """Gestiona el estado del disyuntor (Circuit Breaker) para un dominio destino."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT consecutive_errors, tripped FROM circuit_state WHERE domain = ?;",
                (domain,),
            ).fetchone()
            errors, tripped = (row[0], row[1]) if row else (0, 0)

            if reset:
                conn.execute(
                    "INSERT OR REPLACE INTO circuit_state (domain, consecutive_errors, tripped, last_failure_timestamp) VALUES (?, 0, 0, ?);",
                    (domain, time.time()),
                )
                return False

            if is_error:
                errors += 1
                if errors >= self.config.max_consecutive_errors:
                    tripped = 1
                conn.execute(
                    "INSERT OR REPLACE INTO circuit_state (domain, consecutive_errors, tripped, last_failure_timestamp) VALUES (?, ?, ?, ?);",
                    (domain, errors, tripped, time.time()),
                )
            return bool(tripped)

    def evaluate_payment_intent(self, intent: ProxyPaymentIntent) -> PolicyEvaluationResult:
        """
        Evalúa deterministamente una intención de pago agéntico M2M contra las 5 capas de gobernanza.
        Retorna el veredicto con código HTTP y justificación matemática.
        """
        parsed = urlparse(intent.target_url)
        domain = parsed.hostname or ""
        payload_hash = hashlib.sha256(json.dumps(intent.payload, sort_keys=True).encode()).hexdigest()

        # FIN-01: Verificación estricta de Allowlist (mitiga Financial Prompt Injection)
        if domain not in self.config.allowlist_domains:
            self.log_event(
                intent.agent_id, intent.target_url, intent.amount_usd,
                "BLOCKED", f"Dominio no autorizado: {domain}", payload_hash=payload_hash,
            )
            return PolicyEvaluationResult(
                decision="BLOCKED",
                status_code=403,
                reason=f"FIN-01: Dominio no autorizado en allowlist: {domain}",
                domain=domain,
                agent_id=intent.agent_id,
                amount_usd=intent.amount_usd,
            )

        # FIN-02: Verificación del Circuit Breaker (bloquea bucles de pago fallidos)
        if self.check_and_update_circuit(domain):
            self.log_event(
                intent.agent_id, intent.target_url, intent.amount_usd,
                "BLOCKED", f"Circuit breaker activo para {domain}", payload_hash=payload_hash,
            )
            return PolicyEvaluationResult(
                decision="BLOCKED",
                status_code=503,
                reason=f"FIN-02: Circuit breaker activo para {domain}. Requiere revisión humana por fallos repetidos post-pago.",
                domain=domain,
                agent_id=intent.agent_id,
                amount_usd=intent.amount_usd,
                circuit_tripped=True,
            )

        # FIN-05: Validación de cabeceras de reto HTTP 402 si están presentes
        if intent.challenge_headers:
            challenge_raw = intent.challenge_headers.get("X-PAYMENT-REQUIRED") or intent.challenge_headers.get("x-payment-required")
            if challenge_raw:
                try:
                    challenge_dict = json.loads(challenge_raw)
                    if "amount_usd" not in challenge_dict:
                        raise ValueError("Falta campo amount_usd en reto 402")
                except (json.JSONDecodeError, ValueError) as exc:
                    self.check_and_update_circuit(domain, is_error=True)
                    self.log_event(
                        intent.agent_id, intent.target_url, intent.amount_usd,
                        "ERROR", f"Reto HTTP 402 malformado: {exc}", payload_hash=payload_hash,
                    )
                    return PolicyEvaluationResult(
                        decision="ERROR",
                        status_code=502,
                        reason=f"FIN-05: Reto HTTP 402 malformado emitido por el proveedor: {exc}",
                        domain=domain,
                        agent_id=intent.agent_id,
                        amount_usd=intent.amount_usd,
                    )

        # FIN-04 B: Umbral de Intervención Humana (HITL) ante montos elevados
        if intent.amount_usd > self.config.hitl_threshold_usd:
            self.log_event(
                intent.agent_id, intent.target_url, intent.amount_usd,
                "PENDING_HITL", f"Excede umbral HITL (${self.config.hitl_threshold_usd})", payload_hash=payload_hash,
            )
            return PolicyEvaluationResult(
                decision="PENDING_HITL",
                status_code=202,
                reason=f"FIN-04: Transacción pausada. Monto ${intent.amount_usd:.2f} supera el umbral autónomo HITL de ${self.config.hitl_threshold_usd:.2f}.",
                domain=domain,
                agent_id=intent.agent_id,
                amount_usd=intent.amount_usd,
            )

        # FIN-04 A: Límite estricto por transacción
        if intent.amount_usd > self.config.max_per_tx_usd:
            self.log_event(
                intent.agent_id, intent.target_url, intent.amount_usd,
                "BLOCKED", f"Excede límite por TX (${self.config.max_per_tx_usd})", payload_hash=payload_hash,
            )
            return PolicyEvaluationResult(
                decision="BLOCKED",
                status_code=403,
                reason=f"FIN-04: Monto ${intent.amount_usd:.2f} excede el límite máximo por transacción (${self.config.max_per_tx_usd:.2f}).",
                domain=domain,
                agent_id=intent.agent_id,
                amount_usd=intent.amount_usd,
            )

        # FIN-03: Control de velocidad y presupuesto acumulado (Horario y Diario)
        spent_hour = self.get_spent(intent.agent_id, 3600)
        if spent_hour + intent.amount_usd > self.config.max_per_hour_usd:
            self.log_event(
                intent.agent_id, intent.target_url, intent.amount_usd,
                "BLOCKED", "Presupuesto horario agotado", payload_hash=payload_hash,
            )
            return PolicyEvaluationResult(
                decision="BLOCKED",
                status_code=429,
                reason=f"FIN-03: Presupuesto por hora agotado. Gastado: ${spent_hour:.2f}, Solicitado: ${intent.amount_usd:.2f}, Límite: ${self.config.max_per_hour_usd:.2f}.",
                domain=domain,
                agent_id=intent.agent_id,
                amount_usd=intent.amount_usd,
                spent_hour_usd=spent_hour,
            )

        spent_day = self.get_spent(intent.agent_id, 86400)
        if spent_day + intent.amount_usd > self.config.max_per_day_usd:
            self.log_event(
                intent.agent_id, intent.target_url, intent.amount_usd,
                "BLOCKED", "Presupuesto diario agotado", payload_hash=payload_hash,
            )
            return PolicyEvaluationResult(
                decision="BLOCKED",
                status_code=429,
                reason=f"FIN-03: Presupuesto diario agotado. Gastado: ${spent_day:.2f}, Solicitado: ${intent.amount_usd:.2f}, Límite: ${self.config.max_per_day_usd:.2f}.",
                domain=domain,
                agent_id=intent.agent_id,
                amount_usd=intent.amount_usd,
                spent_day_usd=spent_day,
            )

        # APROBADO: Todas las políticas financieras han sido superadas
        return PolicyEvaluationResult(
            decision="ALLOWED",
            status_code=200,
            reason="Gobernanza financiera superada. Transacción autorizada.",
            domain=domain,
            agent_id=intent.agent_id,
            amount_usd=intent.amount_usd,
            spent_hour_usd=spent_hour,
            spent_day_usd=spent_day,
        )

    def record_payment_result(
        self,
        agent_id: str,
        target_url: str,
        amount_usd: float,
        success: bool,
        tx_hash: str = "",
        error_detail: str = "",
    ) -> None:
        """Registra el desenlace de la transacción y ajusta el estado del disyuntor."""
        parsed = urlparse(target_url)
        domain = parsed.hostname or ""

        if success:
            self.check_and_update_circuit(domain, reset=True)
            self.log_event(
                agent_id, target_url, amount_usd,
                "PAID_SUCCESS", "Transacción completada exitosamente", tx_hash=tx_hash,
            )
        else:
            self.check_and_update_circuit(domain, is_error=True)
            self.log_event(
                agent_id, target_url, amount_usd,
                "PAID_FAILED_DELIVERY", error_detail or "Fallo de entrega post-pago", tx_hash=tx_hash,
            )

    def orchestrate_saga(
        self,
        saga_id: str,
        steps: list[SagaStep],
    ) -> SagaExecutionResult:
        """
        Orquesta una transacción distribuida multi-agente M2M bajo el patrón Saga.
        Si algún paso falla, ejecuta transacciones compensatorias en orden inverso.
        """
        execution_trail: list[dict] = []
        completed_steps: list[SagaStep] = []
        total_cost = 0.0

        for idx, step in enumerate(steps, 1):
            step_record = {
                "step_index": idx,
                "step_id": step.step_id,
                "agent_id": step.agent_id,
                "service_name": step.service_name,
                "cost_usd": step.cost_usd,
                "timestamp": time.time(),
            }

            # Simulación o ejecución del paso (falla si el payload tiene "simulate_failure": True)
            if step.payload.get("simulate_failure"):
                step_record["status"] = "FAILED"
                step_record["error"] = step.payload.get("failure_reason", "Error inducido en paso")
                execution_trail.append(step_record)

                # Iniciar compensación en orden inverso
                compensated_count = 0
                for comp_step in reversed(completed_steps):
                    comp_record = {
                        "compensation_for": comp_step.step_id,
                        "agent_id": comp_step.agent_id,
                        "service_name": comp_step.service_name,
                        "action": "COMPENSATED",
                        "refund_amount_usd": comp_step.cost_usd,
                        "timestamp": time.time(),
                    }
                    total_cost -= comp_step.cost_usd
                    execution_trail.append(comp_record)
                    compensated_count += 1

                res = SagaExecutionResult(
                    saga_id=saga_id,
                    status="COMPENSATED",
                    steps_executed=len(completed_steps),
                    steps_compensated=compensated_count,
                    total_cost_usd=max(0.0, total_cost),
                    execution_trail=execution_trail,
                    error_detail=step_record.get("error"),
                )
                self._persist_saga_record(res)
                return res

            step_record["status"] = "SUCCESS"
            total_cost += step.cost_usd
            execution_trail.append(step_record)
            completed_steps.append(step)

        res = SagaExecutionResult(
            saga_id=saga_id,
            status="COMPLETED",
            steps_executed=len(completed_steps),
            steps_compensated=0,
            total_cost_usd=total_cost,
            execution_trail=execution_trail,
            error_detail=None,
        )
        self._persist_saga_record(res)
        return res

    def _persist_saga_record(self, saga: SagaExecutionResult) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO saga_records (saga_id, status, timestamp, steps_count, trail_json)
                VALUES (?, ?, ?, ?, ?);
                """,
                (saga.saga_id, saga.status, time.time(), saga.steps_executed, json.dumps(saga.execution_trail)),
            )

    def get_audit_summary(self, agent_id: str | None = None) -> dict:
        """Retorna resumen métrico de la bitácora financiera y estado de disyuntores."""
        with self._get_connection() as conn:
            query = "SELECT status, COUNT(*), COALESCE(SUM(amount_usd), 0.0) FROM audit_log"
            params = []
            if agent_id:
                query += " WHERE agent_id = ?"
                params.append(agent_id)
            query += " GROUP BY status;"
            rows = conn.execute(query, params).fetchall()

            status_metrics = {r[0]: {"count": r[1], "sum_usd": r[2]} for r in rows}

            circuits = conn.execute("SELECT domain, consecutive_errors, tripped FROM circuit_state;").fetchall()
            circuit_states = {c[0]: {"consecutive_errors": c[1], "tripped": bool(c[2])} for c in circuits}

            recent_events = conn.execute(
                "SELECT id, timestamp, agent_id, target_url, amount_usd, status, reason FROM audit_log ORDER BY id DESC LIMIT 10;"
            ).fetchall()

            events_list = [
                {
                    "id": e[0],
                    "timestamp": e[1],
                    "agent_id": e[2],
                    "target_url": e[3],
                    "amount_usd": e[4],
                    "status": e[5],
                    "reason": e[6],
                }
                for e in recent_events
            ]

            return {
                "status_breakdown": status_metrics,
                "active_circuits": circuit_states,
                "recent_audit_events": events_list,
            }
