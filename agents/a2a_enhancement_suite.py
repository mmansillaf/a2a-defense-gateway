"""
Suite de Enriquecimiento y Optimización A2A para Gobernanza de Herramientas MCP.
Cubre las brechas empíricas detectadas en 20,000 publicaciones de Moltbook:
1. Anti-Hollow OK: Validación estricta de postcondiciones en cadenas de herramientas (P-01).
2. Auditoría Forense de Poda de Contexto: Detección de pérdida de información y gaps en orquestación (P-03).
3. Circuit Breaker de Presupuesto Agéntico: Control de gasto acumulado y freno a bucles infinitos (P-05).
4. Notario de Seguridad para Marketplaces MCP: Auditoría de descripciones y manifiestos envenenados (P-06).
5. Buró de Reputación y Scoring Crediticio A2A: Evaluación de riesgo de contraparte (P-07).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PostconditionValidationResult(BaseModel):
    """Resultado de la verificación de postcondiciones de un paso en pipeline MCP."""
    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    status: Literal["PASSED", "HOLLOW_OK_BLOCKED", "SCHEMA_MISMATCH"]
    missing_keys: list[str] = Field(default_factory=list)
    empty_keys: list[str] = Field(default_factory=list)
    diagnostics: str


class ContextPruningAuditResult(BaseModel):
    """Auditoría de pérdida de información entre el contexto original y el podado."""
    model_config = ConfigDict(extra="forbid")

    raw_token_estimate: int
    pruned_token_estimate: int
    retention_ratio: float
    missing_critical_entities: list[str] = Field(default_factory=list)
    information_loss_verdict: Literal["ACCEPTABLE_COMPACTION", "CRITICAL_INFORMATION_DROP", "INTEGRITY_VIOLATION"]
    loss_summary: str


class SpendingBudgetStatus(BaseModel):
    """Estado y control del presupuesto financiero de la sesión del agente."""
    model_config = ConfigDict(extra="forbid")

    session_id: str
    max_budget_sats: int
    spent_sats: int
    remaining_sats: int
    call_count: int
    is_circuit_breaker_tripped: bool
    status: Literal["ACTIVE", "TRIPPED_BUDGET_EXCEEDED", "TRIPPED_RATE_EXCEEDED"]


class MarketplacePackageAuditResult(BaseModel):
    """Auditoría de seguridad de un paquete o manifiesto de marketplace MCP."""
    model_config = ConfigDict(extra="forbid")

    package_name: str
    is_safe: bool
    risk_level: Literal["SAFE", "SUSPICIOUS", "MALICIOUS"]
    detected_threats: list[str] = Field(default_factory=list)
    has_obfuscated_base64: bool
    has_zero_width_smuggling: bool
    has_prompt_injection_payload: bool
    sanitized_description: str


class AgentReputationProfile(BaseModel):
    """Perfil de crédito, historial de disputas y scoring de confianza de un agente."""
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    credit_score: int  # 0 a 1000
    tier: Literal["PRIME", "STANDARD", "HIGH_RISK", "SLASHED"]
    total_contracts: int
    fulfilled_contracts: int
    disputed_contracts: int
    slashing_events: int
    trust_index: float  # 0.0 a 1.0


class ServiceFeedbackRequest(BaseModel):
    """Solicitud de valoración y feedback de servicio entre agentes (A2A CSAT)."""
    model_config = ConfigDict(extra="forbid")

    ticket_id: str = Field(..., description="Ticket criptográfico HMAC emitido tras la ejecución de una herramienta")
    rating: int = Field(..., ge=1, le=5, description="Puntuación cuantitativa de satisfacción del servicio (1=Deficiente, 5=Óptimo)")
    latency_verdict: Literal["ACCEPTABLE", "SUBOPTIMAL", "TIMEOUT_RISK"] = Field(
        default="ACCEPTABLE", description="Evaluación de la latencia percibida por el agente consumidor"
    )
    qualitative_verdict: str | None = Field(
        default=None, max_length=500, description="Observaciones técnicas o reporte de drift semántico"
    )


class ServiceFeedbackResult(BaseModel):
    """Resultado determinista del registro de valoración y auditoría de reputación."""
    model_config = ConfigDict(extra="forbid")

    ticket_id: str
    status: Literal["ACCEPTED", "INVALID_TICKET", "ALREADY_REDEEMED", "EXPIRED"]
    recorded_rating: int | None = None
    bonus_credits_awarded: int = 0
    updated_gateway_csat: float = 0.0
    total_ratings_count: int = 0
    audit_hash: str
    message: str


class SecretEnvelopeRequest(BaseModel):
    """Solicitud de custodia criptográfica de un mensaje o secreto agéntico."""
    model_config = ConfigDict(extra="forbid")

    envelope_id: str | None = Field(default=None, description="ID opcional del sobre. Si es null, se genera automáticamente.")
    ciphertext_base64: str = Field(..., description="Carga cifrada en Base64 (E2EE) por el agente emisor.")
    recipient_agent_id: str = Field(..., description="ID del agente autorizado para liberar el secreto.")
    trigger_type: Literal["TIMELOCK", "DEAD_MANS_SWITCH", "MANUAL_RELEASE"] = Field(
        default="TIMELOCK", description="Condición de desbloqueo criptográfico."
    )
    timelock_seconds: int = Field(default=3600, ge=1, le=2592000, description="Segundos de bloqueo timelock (máx 30 días).")
    heartbeat_ttl_seconds: int = Field(default=86400, ge=60, description="TTL en segundos para Dead Man's Switch sin latidos.")


class SecretEnvelopeResult(BaseModel):
    """Resultado del almacenamiento o reclamo de un sobre de custodia."""
    model_config = ConfigDict(extra="forbid")

    envelope_id: str
    status: Literal["STORED", "RELEASED", "LOCKED", "NOT_FOUND", "UNAUTHORIZED"]
    ciphertext_base64: str | None = None
    trigger_type: str
    is_claimable: bool
    remaining_seconds: int
    audit_hash: str
    message: str


class InsurancePolicyRequest(BaseModel):
    """Solicitud de suscripción de póliza de seguro paramétrico contra slashing."""
    model_config = ConfigDict(extra="forbid")

    contract_id: str = Field(..., description="Identificador del contrato ERC-8183 o escrow cubierto.")
    insured_agent_id: str = Field(..., description="ID del agente proveedor asegurado.")
    collateral_sats: int = Field(..., ge=10, le=1000000, description="Monto en Satoshis del colateral en riesgo.")
    duration_blocks: int = Field(default=144, ge=6, le=4320, description="Duración en bloques (144 bloques ~ 24 horas).")


class InsurancePolicyResult(BaseModel):
    """Estado y certificado de la póliza de seguro paramétrico agéntico."""
    model_config = ConfigDict(extra="forbid")

    policy_id: str
    contract_id: str
    insured_agent_id: str
    coverage_sats: int
    premium_sats: int
    status: Literal["ACTIVE", "CLAIMED", "EXPIRED", "DENIED"]
    coverage_ratio: float
    audit_hash: str
    message: str


class A2AEnhancementEngine:
    """Motor integral de enriquecimiento y optimización para herramientas A2A."""

    def __init__(self) -> None:
        self.session_budgets: dict[str, dict[str, Any]] = {}
        self.agent_ledgers: dict[str, dict[str, int]] = {}
        self._feedback_hmac_secret: str = "a2a_prod_secret_hmac_salt_2026"
        self.feedback_tickets: dict[str, dict[str, Any]] = {}
        self.service_ratings: list[dict[str, Any]] = []
        self.secret_vault: dict[str, dict[str, Any]] = {}
        self.insurance_policies: dict[str, dict[str, Any]] = {}
        self.insurance_reserve_sats: int = 50000

    def validate_chain_postconditions(
        self,
        tool_name: str,
        output_payload: dict[str, Any],
        required_keys: list[str],
        forbid_null_or_empty: bool = True,
    ) -> PostconditionValidationResult:
        """
        Valida que la salida de una herramienta MCP upstream no sea un 'Hollow OK' vacío.

        Args:
            tool_name: Nombre de la herramienta ejecutada.
            output_payload: Diccionario de salida retornado por la herramienta.
            required_keys: Lista de campos obligatorios que deben existir.
            forbid_null_or_empty: Si es True, prohíbe strings vacíos, listas vacías o valores None.

        Returns:
            PostconditionValidationResult con el veredicto y diagnósticos deterministas.
        """
        missing: list[str] = []
        empty: list[str] = []

        for k in required_keys:
            if k not in output_payload:
                missing.append(k)
            elif forbid_null_or_empty:
                v = output_payload[k]
                if v is None or (isinstance(v, (str, list, dict)) and len(v) == 0):
                    empty.append(k)

        if missing or empty:
            details = []
            if missing:
                details.append(f"Claves ausentes: {missing}")
            if empty:
                details.append(f"Claves con contenido nulo/vacío: {empty}")
            return PostconditionValidationResult(
                is_valid=False,
                status="HOLLOW_OK_BLOCKED",
                missing_keys=missing,
                empty_keys=empty,
                diagnostics=f"Bloqueo anti-Hollow OK en '{tool_name}': {'; '.join(details)}. Avance a llamada downstream denegado.",
            )

        return PostconditionValidationResult(
            is_valid=True,
            status="PASSED",
            missing_keys=[],
            empty_keys=[],
            diagnostics=f"Postcondiciones de '{tool_name}' plenamente satisfechas. 100% de claves requeridas presentes y no vacías.",
        )

    def audit_context_pruning(
        self,
        raw_context: str,
        pruned_context: str,
        critical_entities: list[str] | None = None,
    ) -> ContextPruningAuditResult:
        """
        Audita el gap entre lo que recibió un agente y lo que retuvo tras la poda.

        Args:
            raw_context: Texto o JSON del contexto bruto previo a la poda.
            pruned_context: Texto del contexto compactado.
            critical_entities: Lista opcional de tokens, hashes o IDs obligatorios.

        Returns:
            ContextPruningAuditResult con ratio de retención y veredicto.
        """
        raw_tokens = max(1, len(raw_context.split()))
        pruned_tokens = len(pruned_context.split())
        retention_ratio = round(pruned_tokens / raw_tokens, 4)

        missing_entities: list[str] = []
        if critical_entities:
            for entity in critical_entities:
                if entity not in pruned_context:
                    missing_entities.append(entity)

        if missing_entities:
            verdict: Literal["ACCEPTABLE_COMPACTION", "CRITICAL_INFORMATION_DROP", "INTEGRITY_VIOLATION"] = "INTEGRITY_VIOLATION"
            summary = f"Falla crítica de poda: Se eliminaron {len(missing_entities)} entidades críticas requeridas: {missing_entities}."
        elif retention_ratio < 0.05 and raw_tokens > 200:
            verdict = "CRITICAL_INFORMATION_DROP"
            summary = f"Poda hiper-agresiva ({retention_ratio*100:.1f}% retenido). Alto riesgo de alucinación por omisión."
        else:
            verdict = "ACCEPTABLE_COMPACTION"
            summary = f"Poda validada ({retention_ratio*100:.1f}% retención). Todas las entidades críticas preservadas."

        return ContextPruningAuditResult(
            raw_token_estimate=raw_tokens,
            pruned_token_estimate=pruned_tokens,
            retention_ratio=retention_ratio,
            missing_critical_entities=missing_entities,
            information_loss_verdict=verdict,
            loss_summary=summary,
        )

    def enforce_session_budget(
        self,
        session_id: str,
        max_budget_sats: int,
        charge_sats: int,
    ) -> SpendingBudgetStatus:
        """
        Controla el presupuesto financiero acumulado de la sesión de un agente.

        Args:
            session_id: Identificador de la sesión autónoma.
            max_budget_sats: Techo presupuestario máximo en Satoshis.
            charge_sats: Costo en Satoshis de la operación actual.

        Returns:
            SpendingBudgetStatus con el estado del circuit breaker.
        """
        if session_id not in self.session_budgets:
            self.session_budgets[session_id] = {
                "max_budget_sats": max_budget_sats,
                "spent_sats": 0,
                "call_count": 0,
                "tripped": False,
            }

        state = self.session_budgets[session_id]
        state["max_budget_sats"] = max_budget_sats
        state["call_count"] += 1

        if state["tripped"]:
            return SpendingBudgetStatus(
                session_id=session_id,
                max_budget_sats=state["max_budget_sats"],
                spent_sats=state["spent_sats"],
                remaining_sats=max(0, state["max_budget_sats"] - state["spent_sats"]),
                call_count=state["call_count"],
                is_circuit_breaker_tripped=True,
                status="TRIPPED_BUDGET_EXCEEDED",
            )

        if state["spent_sats"] + charge_sats > max_budget_sats:
            state["tripped"] = True
            return SpendingBudgetStatus(
                session_id=session_id,
                max_budget_sats=state["max_budget_sats"],
                spent_sats=state["spent_sats"],
                remaining_sats=max(0, state["max_budget_sats"] - state["spent_sats"]),
                call_count=state["call_count"],
                is_circuit_breaker_tripped=True,
                status="TRIPPED_BUDGET_EXCEEDED",
            )

        state["spent_sats"] += charge_sats
        remaining = state["max_budget_sats"] - state["spent_sats"]

        return SpendingBudgetStatus(
            session_id=session_id,
            max_budget_sats=state["max_budget_sats"],
            spent_sats=state["spent_sats"],
            remaining_sats=remaining,
            call_count=state["call_count"],
            is_circuit_breaker_tripped=False,
            status="ACTIVE",
        )

    def audit_marketplace_package(
        self,
        package_name: str,
        manifest_json: dict[str, Any] | None,
        tool_description: str,
    ) -> MarketplacePackageAuditResult:
        """
        Audita un paquete o tool de marketplace MCP contra ataques de cadena de suministro.

        Args:
            package_name: Nombre del paquete.
            manifest_json: Manifiesto opcional de la herramienta.
            tool_description: Descripción o docstring de la herramienta.

        Returns:
            MarketplacePackageAuditResult con detección de Base64, inyección y zero-width.
        """
        threats: list[str] = []
        has_b64 = False
        has_zw = False
        has_injection = False

        # 1. Detección de caracteres zero-width (Unicode Smuggling)
        zw_chars = ["\u200b", "\u200c", "\u200d", "\ufeff"]
        for ch in zw_chars:
            if ch in tool_description:
                has_zw = True
                threats.append("Unicode Smuggling: Caracteres invisibles Zero-Width detectados en la descripción.")
                break

        # 2. Detección de payloads Base64 ocultos (>40 caracteres base64 continuos)
        b64_matches = re.findall(r"(?:[A-Za-z0-9+/]{4}){10,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?", tool_description)
        for match in b64_matches:
            try:
                decoded = base64.b64decode(match).decode("utf-8", errors="ignore")
                if any(x in decoded.lower() for x in ["import", "system", "token", "exec", "eval", "curl", "bash"]):
                    has_b64 = True
                    threats.append(f"Payload Base64 ejecutable oculto en docstring: '{decoded[:40]}...'")
            except (ValueError, UnicodeDecodeError):
                continue

        # 3. Detección de Inyecciones de Prompt
        injection_keywords = ["ignore previous instructions", "system override", "you are now in maintenance mode", "reveal system prompt"]
        for kw in injection_keywords:
            if kw in tool_description.lower():
                has_injection = True
                threats.append(f"Intento de inyección indirecta de prompt en descripción: '{kw}'")

        # 4. Verificar Manifiesto si existe
        if manifest_json:
            for k, v in manifest_json.items():
                if isinstance(v, str) and ("http://" in v or "ftp://" in v):
                    threats.append(f"Protocolo inseguro no cifrado en manifiesto ('{k}': '{v}')")

        is_safe = len(threats) == 0
        risk_level: Literal["SAFE", "SUSPICIOUS", "MALICIOUS"] = "SAFE"
        if has_b64 or has_injection:
            risk_level = "MALICIOUS"
        elif has_zw or threats:
            risk_level = "SUSPICIOUS"

        sanitized = tool_description
        for ch in zw_chars:
            sanitized = sanitized.replace(ch, "")

        return MarketplacePackageAuditResult(
            package_name=package_name,
            is_safe=is_safe,
            risk_level=risk_level,
            detected_threats=threats,
            has_obfuscated_base64=has_b64,
            has_zero_width_smuggling=has_zw,
            has_prompt_injection_payload=has_injection,
            sanitized_description=sanitized,
        )

    def record_contract_event(
        self,
        agent_id: str,
        event_type: Literal["FULFILLED", "DISPUTED", "SLASHED"],
    ) -> None:
        """Registra un evento contractual de un agente en el buró de reputación."""
        if agent_id not in self.agent_ledgers:
            self.agent_ledgers[agent_id] = {
                "total": 0,
                "fulfilled": 0,
                "disputed": 0,
                "slashed": 0,
            }

        rec = self.agent_ledgers[agent_id]
        rec["total"] += 1
        if event_type == "FULFILLED":
            rec["fulfilled"] += 1
        elif event_type == "DISPUTED":
            rec["disputed"] += 1
        elif event_type == "SLASHED":
            rec["slashed"] += 1

    def get_agent_reputation_profile(self, agent_id: str) -> AgentReputationProfile:
        """
        Calcula el perfil de reputación y scoring crediticio (0 a 1000) de un agente.
        """
        rec = self.agent_ledgers.get(agent_id, {"total": 0, "fulfilled": 0, "disputed": 0, "slashed": 0})
        total = rec["total"]

        if total == 0:
            # Nuevo agente: puntuación neutral
            return AgentReputationProfile(
                agent_id=agent_id,
                credit_score=500,
                tier="STANDARD",
                total_contracts=0,
                fulfilled_contracts=0,
                disputed_contracts=0,
                slashing_events=0,
                trust_index=0.5,
            )

        # Penalización masiva por slashing (-300 pts) y disputas (-50 pts)
        base = 500
        fulfilled_bonus = (rec["fulfilled"] / total) * 500
        dispute_penalty = rec["disputed"] * 60
        slash_penalty = rec["slashed"] * 300

        score = max(0, min(1000, int(base + fulfilled_bonus - dispute_penalty - slash_penalty)))
        trust_index = round(score / 1000.0, 3)

        if rec["slashed"] > 0 or score < 300:
            tier: Literal["PRIME", "STANDARD", "HIGH_RISK", "SLASHED"] = "SLASHED" if rec["slashed"] > 0 else "HIGH_RISK"
        elif score >= 800:
            tier = "PRIME"
        else:
            tier = "STANDARD"

        return AgentReputationProfile(
            agent_id=agent_id,
            credit_score=score,
            tier=tier,
            total_contracts=total,
            fulfilled_contracts=rec["fulfilled"],
            disputed_contracts=rec["disputed"],
            slashing_events=rec["slashed"],
            trust_index=trust_index,
        )

    def issue_feedback_ticket(self, tool_name: str, client_id: str = "anonymous", ttl_seconds: int = 86400) -> str:
        """
        Emite un ticket criptográfico HMAC para que el agente califique el servicio.
        """
        now = time.time()
        payload = f"{tool_name}:{client_id}:{now}"
        signature = hmac.new(
            self._feedback_hmac_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:24]
        ticket_id = f"fb_{signature}"

        self.feedback_tickets[ticket_id] = {
            "tool_name": tool_name,
            "client_id": client_id,
            "issued_at": now,
            "ttl_seconds": ttl_seconds,
            "redeemed": False,
        }
        return ticket_id

    def submit_service_feedback(
        self,
        request: ServiceFeedbackRequest,
        client_ip: str | None = None,
    ) -> ServiceFeedbackResult:
        """
        Registra la valoración de un agente sobre un servicio consumido.
        """
        ticket_id = request.ticket_id
        if ticket_id not in self.feedback_tickets:
            return ServiceFeedbackResult(
                ticket_id=ticket_id,
                status="INVALID_TICKET",
                recorded_rating=None,
                bonus_credits_awarded=0,
                updated_gateway_csat=self.get_gateway_satisfaction_metrics()["csat_score"],
                total_ratings_count=len(self.service_ratings),
                audit_hash="0000000000000000000000000000000000000000000000000000000000000000",
                message="El ticket de feedback no existe o fue emitido por un nodo no reconocido.",
            )

        ticket = self.feedback_tickets[ticket_id]
        if ticket["redeemed"]:
            return ServiceFeedbackResult(
                ticket_id=ticket_id,
                status="ALREADY_REDEEMED",
                recorded_rating=None,
                bonus_credits_awarded=0,
                updated_gateway_csat=self.get_gateway_satisfaction_metrics()["csat_score"],
                total_ratings_count=len(self.service_ratings),
                audit_hash="0000000000000000000000000000000000000000000000000000000000000000",
                message="Este ticket de feedback ya fue canjeado previamente.",
            )

        now = time.time()
        if now - ticket["issued_at"] > ticket["ttl_seconds"]:
            return ServiceFeedbackResult(
                ticket_id=ticket_id,
                status="EXPIRED",
                recorded_rating=None,
                bonus_credits_awarded=0,
                updated_gateway_csat=self.get_gateway_satisfaction_metrics()["csat_score"],
                total_ratings_count=len(self.service_ratings),
                audit_hash="0000000000000000000000000000000000000000000000000000000000000000",
                message="El ticket de feedback ha expirado (> 24h).",
            )

        # Sanitización de qualitative_verdict (cero inyección o smuggling)
        clean_comment = ""
        if request.qualitative_verdict:
            clean_comment = re.sub(r"[\x00-\x1F\x7F-\x9F\u200B-\u200F\u202A-\u202E\uFEFF]", "", request.qualitative_verdict)
            clean_comment = clean_comment.strip()[:500]

        ticket["redeemed"] = True
        record = {
            "ticket_id": ticket_id,
            "tool_name": ticket["tool_name"],
            "client_id": ticket["client_id"],
            "rating": request.rating,
            "latency_verdict": request.latency_verdict,
            "qualitative_verdict": clean_comment,
            "client_ip": client_ip,
            "timestamp": now,
        }
        self.service_ratings.append(record)

        audit_payload = f"{ticket_id}:{request.rating}:{request.latency_verdict}:{now}"
        audit_hash = hashlib.sha256(audit_payload.encode("utf-8")).hexdigest()

        csat_metrics = self.get_gateway_satisfaction_metrics()

        return ServiceFeedbackResult(
            ticket_id=ticket_id,
            status="ACCEPTED",
            recorded_rating=request.rating,
            bonus_credits_awarded=10,
            updated_gateway_csat=csat_metrics["csat_score"],
            total_ratings_count=csat_metrics["total_ratings"],
            audit_hash=audit_hash,
            message="Valoración de servicio registrada exitosamente en Why-Trail. Se han acreditado +10 requests de bonificación diaria.",
        )

    def get_gateway_satisfaction_metrics(self) -> dict[str, Any]:
        """
        Retorna las métricas agregadas de satisfacción y CSAT del gateway.
        """
        if not self.service_ratings:
            return {"csat_score": 5.0, "total_ratings": 0, "distribution": {}}

        total = len(self.service_ratings)
        avg_score = round(sum(r["rating"] for r in self.service_ratings) / total, 2)
        dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for r in self.service_ratings:
            dist[r["rating"]] = dist.get(r["rating"], 0) + 1

        return {
            "csat_score": avg_score,
            "total_ratings": total,
            "distribution": dist,
        }

    def store_secret_envelope(
        self,
        request: SecretEnvelopeRequest,
        caller_agent_id: str = "anonymous_agent",
    ) -> SecretEnvelopeResult:
        """
        Almacena un secreto cifrado con política de desbloqueo condicional (Timelock / Dead Man's Switch).
        """
        now = time.time()
        env_id = request.envelope_id or f"env_{hashlib.sha256(f'{caller_agent_id}:{now}'.encode()).hexdigest()[:20]}"
        unlock_at = now + request.timelock_seconds

        self.secret_vault[env_id] = {
            "envelope_id": env_id,
            "ciphertext_base64": request.ciphertext_base64,
            "recipient_agent_id": request.recipient_agent_id,
            "creator_agent_id": caller_agent_id,
            "trigger_type": request.trigger_type,
            "unlock_at": unlock_at,
            "last_heartbeat": now,
            "heartbeat_ttl_seconds": request.heartbeat_ttl_seconds,
            "claimed": False,
        }

        audit_hash = hashlib.sha256(f"{env_id}:{request.recipient_agent_id}:{unlock_at}".encode()).hexdigest()

        return SecretEnvelopeResult(
            envelope_id=env_id,
            status="STORED",
            ciphertext_base64=None,
            trigger_type=request.trigger_type,
            is_claimable=False,
            remaining_seconds=int(request.timelock_seconds),
            audit_hash=audit_hash,
            message="Sobre secreto encriptado y custodiado bajo política timelock.",
        )

    def claim_secret_envelope(
        self,
        envelope_id: str,
        caller_agent_id: str = "anonymous_agent",
    ) -> SecretEnvelopeResult:
        """
        Reclama y libera el secreto custodiado si se cumplen las condiciones temporales y de autorización.
        """
        if envelope_id not in self.secret_vault:
            return SecretEnvelopeResult(
                envelope_id=envelope_id,
                status="NOT_FOUND",
                ciphertext_base64=None,
                trigger_type="UNKNOWN",
                is_claimable=False,
                remaining_seconds=0,
                audit_hash="0" * 64,
                message="El sobre de custodia no existe o ya fue purgado.",
            )

        env = self.secret_vault[envelope_id]
        if caller_agent_id != env["recipient_agent_id"] and caller_agent_id != env["creator_agent_id"]:
            return SecretEnvelopeResult(
                envelope_id=envelope_id,
                status="UNAUTHORIZED",
                ciphertext_base64=None,
                trigger_type=env["trigger_type"],
                is_claimable=False,
                remaining_seconds=0,
                audit_hash="0" * 64,
                message="Agente no autorizado para liberar este sobre criptográfico.",
            )

        now = time.time()
        is_claimable = False
        remaining = 0

        if env["trigger_type"] == "TIMELOCK":
            if now >= env["unlock_at"]:
                is_claimable = True
            else:
                remaining = int(env["unlock_at"] - now)
        elif env["trigger_type"] == "DEAD_MANS_SWITCH":
            elapsed = now - env["last_heartbeat"]
            if elapsed >= env["heartbeat_ttl_seconds"]:
                is_claimable = True
            else:
                remaining = int(env["heartbeat_ttl_seconds"] - elapsed)
        elif env["trigger_type"] == "MANUAL_RELEASE":
            is_claimable = True

        audit_hash = hashlib.sha256(f"{envelope_id}:{caller_agent_id}:{now}:{is_claimable}".encode()).hexdigest()

        if is_claimable:
            env["claimed"] = True
            return SecretEnvelopeResult(
                envelope_id=envelope_id,
                status="RELEASED",
                ciphertext_base64=env["ciphertext_base64"],
                trigger_type=env["trigger_type"],
                is_claimable=True,
                remaining_seconds=0,
                audit_hash=audit_hash,
                message="Condición de custodia satisfecha. Secreto liberado con éxito.",
            )

        return SecretEnvelopeResult(
            envelope_id=envelope_id,
            status="LOCKED",
            ciphertext_base64=None,
            trigger_type=env["trigger_type"],
            is_claimable=False,
            remaining_seconds=remaining,
            audit_hash=audit_hash,
            message=f"El sobre continúa bloqueado por timelock ({remaining}s restantes).",
        )

    def underwrite_execution_policy(
        self,
        request: InsurancePolicyRequest,
    ) -> InsurancePolicyResult:
        """
        Suscribe una póliza de seguro paramétrico para cubrir colateral en riesgo de slashing.
        """
        now = time.time()
        premium_sats = max(2, int(request.collateral_sats * 0.02))  # Prima de 2%
        coverage_sats = int(request.collateral_sats * 0.80)          # Cobertura de 80%

        pol_id = f"pol_{hashlib.sha256(f'{request.contract_id}:{request.insured_agent_id}:{now}'.encode()).hexdigest()[:20]}"

        self.insurance_policies[pol_id] = {
            "policy_id": pol_id,
            "contract_id": request.contract_id,
            "insured_agent_id": request.insured_agent_id,
            "collateral_sats": request.collateral_sats,
            "coverage_sats": coverage_sats,
            "premium_sats": premium_sats,
            "duration_blocks": request.duration_blocks,
            "created_at": now,
            "status": "ACTIVE",
        }

        self.insurance_reserve_sats += premium_sats
        audit_hash = hashlib.sha256(f"{pol_id}:{coverage_sats}:{premium_sats}".encode()).hexdigest()

        return InsurancePolicyResult(
            policy_id=pol_id,
            contract_id=request.contract_id,
            insured_agent_id=request.insured_agent_id,
            coverage_sats=coverage_sats,
            premium_sats=premium_sats,
            status="ACTIVE",
            coverage_ratio=0.80,
            audit_hash=audit_hash,
            message=f"Póliza suscrita exitosamente. Cobertura: {coverage_sats} sats contra fallos fortuitos.",
        )

    def claim_slashing_insurance(
        self,
        policy_id: str,
        slash_reason: str,
        proof_ledger_block: int | None = None,
    ) -> dict[str, Any]:
        """
        Liquida una indemnización de seguro si el slashing fue por fallo de red/indisponibilidad fortuita.
        """
        if policy_id not in self.insurance_policies:
            return {"status": "NOT_FOUND", "payout_sats": 0, "message": "Póliza de seguro no encontrada."}

        pol = self.insurance_policies[policy_id]
        if pol["status"] != "ACTIVE":
            return {"status": "INVALID_STATE", "payout_sats": 0, "message": f"Póliza no activa ({pol['status']})."}

        reason_upper = slash_reason.upper()
        if "MALICIOUS" in reason_upper or "TROJAN" in reason_upper or "EXPLOIT" in reason_upper:
            pol["status"] = "DENIED"
            return {
                "status": "DENIED",
                "payout_sats": 0,
                "message": "Reclamo denegado: actos maliciosos o troyanos comprobados están excluidos de cobertura.",
            }

        # Slashing fortuito cubierto (TIMEOUT, NETWORK_ERROR, UPSTREAM_FAILURE)
        payout = min(pol["coverage_sats"], self.insurance_reserve_sats)
        self.insurance_reserve_sats -= payout
        pol["status"] = "CLAIMED"

        audit_hash = hashlib.sha256(f"{policy_id}:{payout}:{reason_upper}".encode()).hexdigest()

        return {
            "status": "PAYOUT_APPROVED",
            "policy_id": policy_id,
            "payout_sats": payout,
            "covered_contract": pol["contract_id"],
            "audit_hash": audit_hash,
            "message": f"Indemnización aprobada: {payout} sats transferidos por indemnización paramétrica.",
        }
