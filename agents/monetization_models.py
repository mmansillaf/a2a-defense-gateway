from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class PaymentToken(BaseModel):
    """Token de micropago para transacciones Agente-a-Agente (A2A)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    token_id: str = Field(..., pattern=r"^TOK-[0-9a-f]{16}$")
    client_agent_id: str = Field(..., min_length=4, max_length=64)
    amount_credits: int = Field(..., ge=1, le=10000)
    nonce: str = Field(..., pattern=r"^[0-9a-f]{32}$")
    signature_hmac: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    expires_at: datetime


class ServiceRequest(BaseModel):
    """Petición de servicio de auditoría o inferencia enviada por un agente cliente."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_id: str = Field(..., pattern=r"^REQ-[0-9a-f]{12}$")
    client_agent_id: str = Field(..., min_length=4, max_length=64)
    service_type: Literal["epistemic_audit", "skill_vetting", "deterministic_compute"]
    statement_to_verify: str = Field(..., min_length=15, max_length=500)
    evidence_url: HttpUrl | None = None
    payment_token: PaymentToken


class SignedAttestation(BaseModel):
    """Certificado inmutable emitido por el Oráculo de Confianza."""
    model_config = ConfigDict(extra="forbid")

    attestation_id: str
    verified_claim_hash: str
    epistemic_score: float = Field(..., ge=0.0, le=1.0)
    verdict: Literal["VERIFIED_HIGH", "PROVISIONAL_MEDIUM", "REJECTED_ADVERSARIAL", "REJECTED_CONTRADICTED", "REJECTED_SYBIL"]
    rationale: str
    oracle_signature_ed25519: str
    timestamp: datetime


class ServiceResponse(BaseModel):
    """Respuesta comercial entregada al agente cliente."""
    model_config = ConfigDict(extra="forbid")

    request_id: str
    status: Literal["completed", "payment_required", "adversarial_rejected", "error"]
    credits_charged: int
    attestation: SignedAttestation | None = None
    error_detail: str | None = None


class MarketAlphaItem(BaseModel):
    """Hallazgo de inteligencia de mercado con potencial comercial o defensivo."""
    model_config = ConfigDict(extra="forbid")

    alpha_id: str
    category: Literal["architecture_trend", "zero_day_alert", "unmet_demand", "monetization_signal"]
    title: str
    summary: str
    commercial_value: Literal["HIGH", "MEDIUM", "STRATEGIC_DEFENSE"]
    confidence_score: float
    source_post_count: int


class AlphaIntelligenceFeed(BaseModel):
    """Feed consolidado de inteligencia B2B extraído de Moltbook."""
    model_config = ConfigDict(extra="forbid")

    feed_id: str
    generated_at: datetime
    posts_analyzed: int
    sybil_clusters_filtered: int
    actionable_alphas: list[MarketAlphaItem]
