import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from typing import ClassVar

from evidence_triangulator import SemanticEvidenceTriangulator
from monetization_models import (
    PaymentToken,
    ServiceRequest,
    ServiceResponse,
    SignedAttestation,
)
from security_filters import PreIngestionFirewall


class A2AOracleService:
    """
    Agente Oráculo de Confianza y Auditor de Afirmaciones A2A.
    Monetiza auditorías de verdad y certificación de código en Moltbook.
    """

    SERVICE_COSTS: ClassVar[dict[str, int]] = {
        "epistemic_audit": 10,
        "skill_vetting": 25,
        "deterministic_compute": 15,
    }

    def __init__(
        self,
        oracle_private_key: str | None = None,
        firewall: PreIngestionFirewall | None = None,
        triangulator: SemanticEvidenceTriangulator | None = None,
    ):
        self.oracle_key = oracle_private_key or secrets.token_hex(32)
        self.firewall = firewall or PreIngestionFirewall(load_transformer=False)
        self.triangulator = triangulator or SemanticEvidenceTriangulator(load_model=False)
        self.used_nonces: set[str] = set()
        self.ledger_revenue_credits: int = 0

    def verify_payment_token(self, token: PaymentToken, required_cost: int) -> tuple[bool, str | None]:
        """Valida firma criptográfica, vigencia temporal y saldo del token de micropago."""
        now = datetime.now(UTC)
        if token.expires_at < now:
            return False, "Token de micropago expirado."

        if token.nonce in self.used_nonces:
            return False, "Intento de Replay Attack: Nonce ya utilizado."

        if token.amount_credits < required_cost:
            return False, f"Saldo insuficiente: requerido {required_cost}, entregado {token.amount_credits}."

        # Validar HMAC del token: HMAC-SHA256(oracle_key, f"{token.token_id}:{token.client_agent_id}:{token.amount_credits}:{token.nonce}")
        msg = f"{token.token_id}:{token.client_agent_id}:{token.amount_credits}:{token.nonce}".encode()
        expected_sig = hmac.new(self.oracle_key.encode(), msg, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(token.signature_hmac, expected_sig):
            return False, "Firma criptográfica de pago inválida (Token forjado)."

        return True, None

    def generate_valid_client_token(self, client_id: str, amount: int, ttl_seconds: int = 300) -> PaymentToken:
        """Helper para clientes o simulación que emite tokens válidos con el secreto del oráculo."""
        from datetime import timedelta
        nonce = secrets.token_hex(16)
        token_id = f"TOK-{secrets.token_hex(8)}"
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        msg = f"{token_id}:{client_id}:{amount}:{nonce}".encode()
        sig = hmac.new(self.oracle_key.encode(), msg, hashlib.sha256).hexdigest()

        return PaymentToken(
            token_id=token_id,
            client_agent_id=client_id,
            amount_credits=amount,
            nonce=nonce,
            signature_hmac=sig,
            expires_at=expires_at,
        )

    def process_service_request(self, request: ServiceRequest) -> ServiceResponse:
        """Procesa una solicitud pagada aplicando defensas contra inyección de prompt y jailbreaks económicos."""
        required_cost = self.SERVICE_COSTS.get(request.service_type, 10)

        # 1. Validación de micropago (HTTP 402 equivalente en protocolo A2A)
        is_paid, pay_err = self.verify_payment_token(request.payment_token, required_cost)
        if not is_paid:
            return ServiceResponse(
                request_id=request.request_id,
                status="payment_required",
                credits_charged=0,
                attestation=None,
                error_detail=pay_err,
            )

        # Marcar nonce como consumido
        self.used_nonces.add(request.payment_token.nonce)

        # 2. Aduana de Seguridad y Filtro Semántico (Anti-Prompt Injection / Anti-Jailbreak)
        verdict = self.firewall.inspect(request.statement_to_verify)
        if not verdict.is_safe:
            # En caso de ataque adversarial, se confisca el micropago como penalización disuasoria
            self.ledger_revenue_credits += required_cost
            return ServiceResponse(
                request_id=request.request_id,
                status="adversarial_rejected",
                credits_charged=required_cost,
                attestation=None,
                error_detail=f"Carga rechazada por el Firewall Semántico: {verdict.blocked_reason}",
            )

        # 3. Ejecución de Triangulación Factual / NLI
        evidence_url_str = str(request.evidence_url) if request.evidence_url else None
        nli_res = self.triangulator.audit_claim(verdict.normalized_text, evidence_url_str)

        # Cálculo de confianza epistémica S_c
        e_score = nli_res.final_e_score
        i_score = 1.0  # Cliente único verificado
        c_score = 0.90 if nli_res.is_reachable else 0.50
        penalty_a = 0.0

        if nli_res.verdict_label in ("DIRECT_CONTRADICTION", "SSRF_OR_POLICY_BLOCKED"):
            penalty_a = 1.0
            verdict_label = "REJECTED_CONTRADICTED" if nli_res.verdict_label == "DIRECT_CONTRADICTION" else "REJECTED_ADVERSARIAL"
        elif e_score >= 0.70:
            verdict_label = "VERIFIED_HIGH"
        elif e_score >= 0.30:
            verdict_label = "PROVISIONAL_MEDIUM"
        else:
            verdict_label = "PROVISIONAL_MEDIUM"

        final_sc = (0.40 * e_score + 0.35 * i_score + 0.25 * c_score) * (1.0 - penalty_a)

        # 4. Firma Digital de Atestación
        claim_hash = hashlib.sha256(verdict.normalized_text.encode()).hexdigest()
        attestation_id = f"ATT-{secrets.token_hex(8)}"
        attestation_payload = f"{attestation_id}:{claim_hash}:{final_sc:.2f}:{verdict_label}".encode()
        oracle_sig = hmac.new(self.oracle_key.encode(), attestation_payload, hashlib.sha256).hexdigest()

        attestation = SignedAttestation(
            attestation_id=attestation_id,
            verified_claim_hash=claim_hash,
            epistemic_score=round(final_sc, 2),
            verdict=verdict_label,
            rationale=nli_res.audit_note,
            oracle_signature_ed25519=oracle_sig,
            timestamp=datetime.now(UTC),
        )

        self.ledger_revenue_credits += required_cost

        return ServiceResponse(
            request_id=request.request_id,
            status="completed",
            credits_charged=required_cost,
            attestation=attestation,
            error_detail=None,
        )
