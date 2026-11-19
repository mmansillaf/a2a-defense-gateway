import math
import secrets
from datetime import UTC, datetime, timedelta
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field


class PricingQuote(BaseModel):
    """Cotización dinámica formal para una solicitud de servicio A2A."""
    model_config = ConfigDict(extra="forbid")

    quote_id: str
    service_type: str
    base_credits: int
    compute_surcharge: int
    risk_surcharge: int
    total_credits: int
    ttl_seconds: int = 180


class OutcomePricingQuote(BaseModel):
    """
    Cotización basada en resultados verificables (Outcome-Based Pricing).
    Alinea el valor económico con hitos de negocio discretos, resolviendo la Paradoja del Innovador.
    """
    model_config = ConfigDict(extra="forbid")

    quote_id: str = Field(..., pattern=r"^OUT-[0-9a-f]{12}$")
    framework_type: Literal["OUTCOME_BASED", "ACTION_USAGE", "SUBSCRIPTION_CREDIT", "FTE_REPLACEMENT"]
    outcome_metric: str  # e.g., 'verified_factual_claim', 'clean_sast_certification'
    fee_per_outcome_credits: int = Field(..., ge=1)
    escrow_deposit_required: int = Field(..., ge=0)
    resolution_layer_timeout_s: int = Field(default=3600)
    created_at: str


class AP2Mandate(BaseModel):
    """
    Mandato de autorización corporativa criptográfica (Agent Payments Protocol - AP2 / MPP).
    Fija límites dinámicos de gasto y plazos temporales para sesiones de streaming de pagos.
    """
    model_config = ConfigDict(extra="forbid")

    mandate_id: str = Field(..., pattern=r"^MND-[0-9a-f]{12}$")
    corporate_principal: str
    delegated_agent_id: str
    spending_limit_credits: int = Field(..., ge=1)
    remaining_credits: int = Field(..., ge=0)
    expires_at: str
    is_active: bool = True


class TokenPricingEngine:
    """
    Motor de tarificación dinámica de servicios y atestaciones en Moltbook.
    Implementa modelos híbridos: Cost-Plus (cómputo + tokens + riesgo),
    Outcome-Based Pricing (cobro por hito resuelto) y Mandatos AP2/MPP.
    """

    BASE_RATES: ClassVar[dict[str, int]] = {
        "epistemic_audit": 10,
        "skill_vetting": 25,
        "deterministic_compute": 15,
        "court_arbitration": 50,
        "grammar_compilation": 12,
    }

    OUTCOME_BENCHMARKS: ClassVar[dict[str, int]] = {
        "verified_factual_resolution": 25,       # Análogo al $0.99 de Intercom Fin
        "certified_malware_free_skill": 50,      # Atestación de seguridad ClawHavoc
        "arbitrated_dispute_settlement": 75,     # Sentencia vinculante Multi-CaMeL
    }

    MARGIN_MULTIPLIER: ClassVar[float] = 1.25  # 25% margen operativo

    def __init__(self, cost_per_100ms_compute: int = 2, cost_per_1k_tokens: int = 1):
        self.compute_rate = cost_per_100ms_compute
        self.token_rate = cost_per_1k_tokens
        self.active_mandates: dict[str, AP2Mandate] = {}

    def calculate_price(
        self,
        service_type: str,
        estimated_compute_ms: int = 50,
        estimated_tokens: int = 500,
        adversarial_risk_score: float = 0.05,
    ) -> PricingQuote:
        """Calcula la tarifa en créditos garantizando cobertura de costos y sobrecargo por riesgo."""
        base = self.BASE_RATES.get(service_type, 10)

        # 1. Componente de Cómputo físico
        compute_cost = math.ceil((estimated_compute_ms / 100.0) * self.compute_rate)
        token_cost = math.ceil((estimated_tokens / 1000.0) * self.token_rate)
        compute_surcharge = int((compute_cost + token_cost) * self.MARGIN_MULTIPLIER)

        # 2. Sobrecargo por Riesgo Adversarial (Seguro contra DoS / Inyecciones)
        if adversarial_risk_score >= 0.50:
            risk_surcharge = math.ceil(base * adversarial_risk_score * 2.0)
        else:
            risk_surcharge = 0

        total = base + compute_surcharge + risk_surcharge

        return PricingQuote(
            quote_id=f"QUO-{secrets.token_hex(6)}",
            service_type=service_type,
            base_credits=base,
            compute_surcharge=compute_surcharge,
            risk_surcharge=risk_surcharge,
            total_credits=total,
            ttl_seconds=180,
        )

    def calculate_outcome_quote(
        self,
        outcome_metric: str,
        difficulty_multiplier: float = 1.0,
    ) -> OutcomePricingQuote:
        """Emite una cotización vinculada estrictamente al éxito del hito verificado."""
        base_fee = self.OUTCOME_BENCHMARKS.get(outcome_metric, 20)
        final_fee = math.ceil(base_fee * max(1.0, difficulty_multiplier))
        deposit_required = math.ceil(final_fee * 1.5)  # 150% de colateral en escrow

        return OutcomePricingQuote(
            quote_id=f"OUT-{secrets.token_hex(6)}",
            framework_type="OUTCOME_BASED",
            outcome_metric=outcome_metric,
            fee_per_outcome_credits=final_fee,
            escrow_deposit_required=deposit_required,
            resolution_layer_timeout_s=3600,
            created_at=datetime.now(UTC).isoformat(),
        )

    def issue_ap2_mandate(
        self,
        corporate_principal: str,
        delegated_agent_id: str,
        spending_limit_credits: int,
        duration_seconds: int = 86400,
    ) -> AP2Mandate:
        """Crea un mandato criptográfico de autorización AP2 con límite de gasto."""
        mandate_id = f"MND-{secrets.token_hex(6)}"
        expires_at = (datetime.now(UTC) + timedelta(seconds=duration_seconds)).isoformat()

        mandate = AP2Mandate(
            mandate_id=mandate_id,
            corporate_principal=corporate_principal,
            delegated_agent_id=delegated_agent_id,
            spending_limit_credits=spending_limit_credits,
            remaining_credits=spending_limit_credits,
            expires_at=expires_at,
            is_active=True,
        )
        self.active_mandates[mandate_id] = mandate
        return mandate

    def deduct_from_mandate(self, mandate_id: str, amount_credits: int) -> bool:
        """Deduce fondos de una sesión MPP/AP2 respetando el límite dinámico."""
        mandate = self.active_mandates.get(mandate_id)
        if not mandate or not mandate.is_active:
            raise ValueError(f"Mandato {mandate_id} inexistente o inactivo.")

        if datetime.now(UTC) > datetime.fromisoformat(mandate.expires_at):
            mandate.is_active = False
            raise ValueError(f"Mandato {mandate_id} ha expirado.")

        if amount_credits > mandate.remaining_credits:
            raise ValueError(
                f"Límite de mandato superado. Saldo: {mandate.remaining_credits}, solicitado: {amount_credits}."
            )

        mandate.remaining_credits -= amount_credits
        return True
