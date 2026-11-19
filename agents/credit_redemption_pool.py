import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field


class RedemptionQuote(BaseModel):
    """Cotización de conversión de créditos internos de Moltbook a Satoshis (Lightning)."""
    model_config = ConfigDict(extra="forbid")

    quote_id: str = Field(..., pattern=r"^QTE-[0-9a-f]{12}$")
    credits: int = Field(..., gt=0)
    exchange_rate_sats_per_credit: int = Field(default=25, gt=0)
    gross_sats: int
    fee_sats: int
    net_sats: int
    expires_at: str


class RedemptionReceipt(BaseModel):
    """Comprobante inmutable de liquidación de créditos a Satoshis."""
    model_config = ConfigDict(extra="forbid")

    redemption_id: str = Field(..., pattern=r"^RED-[0-9a-f]{16}$")
    agent_id: str
    credits_redeemed: int
    net_sats_transferred: int
    lightning_payout_hash: str
    destination_bolt11: str
    timestamp: str
    status: str = "SETTLED"


class CreditRedemptionPool:
    """
    Piscina de redención y liquidación económica A2A.
    Convierte créditos computacionales acumulados a satoshis en Lightning Network (L402 out).
    Tasa fija de anclaje: 1 Crédito = 25 Sats (configurable con spread de seguridad).
    """

    def __init__(
        self,
        exchange_rate_sats_per_credit: int = 25,
        liquidity_reserve_sats: int = 1_000_000,
        fee_basis_points: int = 100,  # 1.0% de comisión por pasarela
    ):
        self.exchange_rate = exchange_rate_sats_per_credit
        self.reserve_sats = liquidity_reserve_sats
        self.fee_bps = fee_basis_points
        self.active_quotes: dict[str, RedemptionQuote] = {}
        self.redemption_history: list[RedemptionReceipt] = []

    def get_quote(self, credits: int, ttl_seconds: int = 300) -> RedemptionQuote:
        """Emite una cotización garantizada temporal para liquidación de créditos."""
        if credits <= 0:
            raise ValueError("La cantidad de créditos a redimir debe ser mayor a 0.")

        gross_sats = credits * self.exchange_rate
        fee_sats = max(1, (gross_sats * self.fee_bps) // 10_000)
        net_sats = gross_sats - fee_sats

        quote_id = f"QTE-{secrets.token_hex(6)}"
        expires_at = (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat()

        quote = RedemptionQuote(
            quote_id=quote_id,
            credits=credits,
            exchange_rate_sats_per_credit=self.exchange_rate,
            gross_sats=gross_sats,
            fee_sats=fee_sats,
            net_sats=net_sats,
            expires_at=expires_at,
        )
        self.active_quotes[quote_id] = quote
        return quote

    def execute_redemption(
        self,
        agent_id: str,
        credits: int,
        destination_bolt11: str,
        quote_id: str | None = None,
    ) -> RedemptionReceipt:
        """
        Ejecuta la liquidación de créditos deduciendo de la reserva y emitiendo pago Lightning simulado.
        """
        if not destination_bolt11 or not destination_bolt11.startswith("lnbc"):
            raise ValueError("Destino de pago inválido. Debe ser una factura o dirección Lightning (lnbc...).")

        if quote_id:
            quote = self.active_quotes.get(quote_id)
            if not quote:
                raise ValueError(f"Cotización {quote_id} no encontrada o inválida.")
            if datetime.now(UTC) > datetime.fromisoformat(quote.expires_at):
                raise ValueError(f"Cotización {quote_id} ha expirado.")
            if quote.credits != credits:
                raise ValueError(f"Discrepancia en créditos: cotizados {quote.credits}, solicitados {credits}.")
            net_sats = quote.net_sats
        else:
            gross = credits * self.exchange_rate
            fee = max(1, (gross * self.fee_bps) // 10_000)
            net_sats = gross - fee

        if net_sats > self.reserve_sats:
            raise ValueError(
                f"Reserva de liquidez insuficiente. Disponible: {self.reserve_sats} sats, requerido: {net_sats} sats."
            )

        # 1. Deducir de reserva
        self.reserve_sats -= net_sats

        # 2. Simular pago de salida Lightning
        payout_preimage = secrets.token_bytes(32)
        payout_hash = hashlib.sha256(payout_preimage).hexdigest()

        receipt = RedemptionReceipt(
            redemption_id=f"RED-{secrets.token_hex(8)}",
            agent_id=agent_id,
            credits_redeemed=credits,
            net_sats_transferred=net_sats,
            lightning_payout_hash=payout_hash,
            destination_bolt11=destination_bolt11,
            timestamp=datetime.now(UTC).isoformat(),
            status="SETTLED",
        )
        self.redemption_history.append(receipt)

        if quote_id and quote_id in self.active_quotes:
            del self.active_quotes[quote_id]

        return receipt
