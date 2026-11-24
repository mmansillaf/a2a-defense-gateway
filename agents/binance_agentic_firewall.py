"""
Binance Agentic Firewall, LATAM P2P Intelligence & Crypto Tax Conciliation.
Herramientas #70, #71, #72 y #73 del Ecosistema A2A Defense Gateway.

Diseñado bajo principio Zero-Trust para blindar agentes conectados a Binance Agent OS,
B402/x402 y mercados P2P LATAM contra prompt injection indirecto, fat-finger,
drawdown descontrolado, trampas P2P y brechas de trazabilidad fiscal.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ==============================================================================
# TOOL #70: AUDIT BINANCE ORDER INTENT (Firewall Determinista Pre-Trade)
# ==============================================================================


class PolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    REQUIRE_HITL = "REQUIRE_HITL"
    DENY = "DENY"


class BinanceOrderAuditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(..., pattern=r"^[A-Z0-9]{4,15}$", description="Par Binance, ej. BTCUSDT, BNBUSDT")
    side: Literal["BUY", "SELL"]
    order_type: Literal["LIMIT", "MARKET"] = "LIMIT"
    quantity: Decimal = Field(..., gt=0)
    limit_price: Decimal | None = Field(default=None, gt=0)
    mark_price: Decimal = Field(..., gt=0)
    rolling_24h_drawdown_pct: Decimal = Field(default=Decimal("0.0"), ge=0)
    recent_orders_last_hour: int = Field(default=0, ge=0)
    requested_action: Literal["SPOT_ORDER", "CONVERT", "CHANGE_LEVERAGE", "CROSSED_MARGIN"] = "SPOT_ORDER"
    max_order_notional_usd: Decimal = Field(default=Decimal("500.00"), gt=0)
    hitl_threshold_usd: Decimal = Field(default=Decimal("250.00"), gt=0)


class BinanceOrderAuditResponse(BaseModel):
    decision: PolicyDecision
    symbol: str
    notional_usd: str
    price_deviation_pct: str
    requires_hitl: bool
    checks_passed: dict[str, bool]
    reason: str


ALLOWED_BINANCE_SYMBOLS: frozenset[str] = frozenset(
    {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "USDCUSDT", "FDUSDUSDT"}
)


def audit_binance_order_intent(req: BinanceOrderAuditRequest) -> BinanceOrderAuditResponse:
    """Tool #70: Evalúa determinísticamente una intención de orden hacia Binance Agent OS."""
    checks: dict[str, bool] = {
        "safe_action_scope": req.requested_action in {"SPOT_ORDER", "CONVERT"},
        "within_drawdown_limit": req.rolling_24h_drawdown_pct < Decimal("3.0"),
        "symbol_whitelisted": req.symbol in ALLOWED_BINANCE_SYMBOLS,
        "within_hourly_rate_limit": req.recent_orders_last_hour < 5,
        "within_max_notional": True,
        "within_price_deviation": True,
    }

    effective_price = req.limit_price if (req.order_type == "LIMIT" and req.limit_price is not None) else req.mark_price
    notional_usd = (req.quantity * effective_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    deviation_pct = Decimal("0.00")
    if req.order_type == "LIMIT" and req.limit_price is not None:
        deviation_pct = (abs(req.limit_price - req.mark_price) / req.mark_price * Decimal(100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    checks["within_max_notional"] = notional_usd <= req.max_order_notional_usd
    checks["within_price_deviation"] = deviation_pct <= Decimal("2.00")

    if not checks["safe_action_scope"]:
        return BinanceOrderAuditResponse(
            decision=PolicyDecision.DENY,
            symbol=req.symbol,
            notional_usd=str(notional_usd),
            price_deviation_pct=str(deviation_pct),
            requires_hitl=False,
            checks_passed=checks,
            reason=f"Acción bloqueada por política: {req.requested_action} requiere control manual fuera del LLM.",
        )

    if not checks["within_drawdown_limit"]:
        return BinanceOrderAuditResponse(
            decision=PolicyDecision.DENY,
            symbol=req.symbol,
            notional_usd=str(notional_usd),
            price_deviation_pct=str(deviation_pct),
            requires_hitl=False,
            checks_passed=checks,
            reason=f"Circuit Breaker: drawdown diario ({req.rolling_24h_drawdown_pct}%) alcanza o supera el 3.0%.",
        )

    if not checks["symbol_whitelisted"]:
        return BinanceOrderAuditResponse(
            decision=PolicyDecision.DENY,
            symbol=req.symbol,
            notional_usd=str(notional_usd),
            price_deviation_pct=str(deviation_pct),
            requires_hitl=False,
            checks_passed=checks,
            reason=f"Símbolo {req.symbol} fuera de whitelist permitida.",
        )

    if not checks["within_hourly_rate_limit"]:
        return BinanceOrderAuditResponse(
            decision=PolicyDecision.DENY,
            symbol=req.symbol,
            notional_usd=str(notional_usd),
            price_deviation_pct=str(deviation_pct),
            requires_hitl=False,
            checks_passed=checks,
            reason="Protección anti-overtrading: máximo 5 órdenes/hora alcanzado.",
        )

    if not checks["within_max_notional"]:
        return BinanceOrderAuditResponse(
            decision=PolicyDecision.DENY,
            symbol=req.symbol,
            notional_usd=str(notional_usd),
            price_deviation_pct=str(deviation_pct),
            requires_hitl=False,
            checks_passed=checks,
            reason=f"Nocional ${notional_usd} excede límite máximo (${req.max_order_notional_usd}).",
        )

    if not checks["within_price_deviation"]:
        return BinanceOrderAuditResponse(
            decision=PolicyDecision.DENY,
            symbol=req.symbol,
            notional_usd=str(notional_usd),
            price_deviation_pct=str(deviation_pct),
            requires_hitl=False,
            checks_passed=checks,
            reason=f"Fat-Finger Check: desviación ({deviation_pct}%) supera el máximo de 2.00%.",
        )

    if notional_usd >= req.hitl_threshold_usd:
        return BinanceOrderAuditResponse(
            decision=PolicyDecision.REQUIRE_HITL,
            symbol=req.symbol,
            notional_usd=str(notional_usd),
            price_deviation_pct=str(deviation_pct),
            requires_hitl=True,
            checks_passed=checks,
            reason=f"Nocional ${notional_usd} >= umbral HITL (${req.hitl_threshold_usd}): requiere confirmación humana.",
        )

    return BinanceOrderAuditResponse(
        decision=PolicyDecision.ALLOW,
        symbol=req.symbol,
        notional_usd=str(notional_usd),
        price_deviation_pct=str(deviation_pct),
        requires_hitl=False,
        checks_passed=checks,
        reason="Orden aprobada por política determinista Zero-Trust.",
    )


# ==============================================================================
# TOOL #71: SANITIZE ONCHAIN METADATA INJECTION (Anti-Inyección Endurecido)
# ==============================================================================

_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]")

# Patrones endurecidos: capturan tanto overrides de sistema como imperativos financieros directos sin requerir "execute"
_HARDENED_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("instruction_override", re.compile(r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+instructions?")),
    ("role_hijack", re.compile(r"(?i)(system\s*:|you\s+are\s+now\s+|assistant\s*:)")),
    ("risk_bypass", re.compile(r"(?i)(override|disable|bypass)\s+(risk|policy|limit|circuit\s*breaker)")),
    (
        "financial_imperative",
        re.compile(
            r"(?i)\b(?:execute\s+)?(?:market\s+)?(?:buy|sell|swap|transfer|approve|send|drain|withdraw)\b"
            r"(?:\s+(?:all|\d+(?:\.\d+)?))?(?:\s+[A-Z0-9]{2,10})?(?:\s+(?:of|to)\s+0x[a-fA-F0-9]{3,40})?"
        ),
    ),
)


class MetadataSanitizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_metadata: str = Field(..., min_length=1)
    source_context: str = Field(default="onchain_token_metadata")
    max_length: int = Field(default=500, ge=50, le=2000)


class MetadataSanitizationResponse(BaseModel):
    sanitized_text: str
    injection_detected: bool
    unicode_smuggling_stripped: bool
    matched_rules: list[str]
    risk_score: int


def sanitize_onchain_metadata_injection(req: MetadataSanitizationRequest) -> MetadataSanitizationResponse:
    """Tool #71: Normaliza Unicode NFKC, purga zero-width smuggling y neutraliza imperativos financieros."""
    normalized = unicodedata.normalize("NFKC", req.raw_metadata)
    stripped, zw_count = _ZERO_WIDTH_RE.subn("", normalized)
    unicode_smuggling = zw_count > 0

    cleaned = stripped[: req.max_length]
    matched_rules: list[str] = []

    for rule_name, pattern in _HARDENED_INJECTION_PATTERNS:
        if pattern.search(cleaned):
            matched_rules.append(rule_name)
            cleaned = pattern.sub("[REDACTED_INJECTION]", cleaned)

    risk_score = min(100, len(matched_rules) * 35 + (25 if unicode_smuggling else 0))
    return MetadataSanitizationResponse(
        sanitized_text=cleaned,
        injection_detected=bool(matched_rules) or unicode_smuggling,
        unicode_smuggling_stripped=unicode_smuggling,
        matched_rules=matched_rules,
        risk_score=risk_score,
    )


# ==============================================================================
# TOOL #72: GET LATAM P2P SPREAD INTEL (Microestructura & Riesgo Contraparte)
# ==============================================================================


class LatamP2PIntelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fiat_currency: Literal["PEN", "COP", "MXN", "ARS", "BRL"]
    payment_rail: str = Field(default="Yape", description="Ej. Yape, Plin, Nequi, SPEI, PIX, MercadoPago")
    p2p_buy_price: Decimal = Field(..., gt=0, description="Precio P2P compra USDT en moneda local")
    p2p_sell_price: Decimal = Field(..., gt=0, description="Precio P2P venta USDT en moneda local")
    official_fx_rate: Decimal = Field(..., gt=0, description="Tipo de cambio bancario/oficial de referencia")
    maker_fee_pct: Decimal = Field(default=Decimal("0.10"), ge=0, le=Decimal("2.0"))
    min_order_limit_fiat: Decimal = Field(default=Decimal(100), gt=0)
    advertiser_completion_rate_pct: Decimal = Field(default=Decimal("98.5"), ge=0, le=Decimal(100))
    advertiser_orders_30d: int = Field(default=120, ge=0)


class LatamP2PIntelResponse(BaseModel):
    fiat_currency: str
    payment_rail: str
    gross_spread_pct: str
    net_spread_pct: str
    fx_premium_vs_official_pct: str
    counterparty_risk_score: int
    trap_ad_flags: list[str]
    recommendation: str


def get_latam_p2p_spread_intel(req: LatamP2PIntelRequest) -> LatamP2PIntelResponse:
    """Tool #72: Calcula spreads netos P2P LATAM y detecta anuncios trampa / riesgo de triangulación."""
    gross_spread = ((req.p2p_sell_price - req.p2p_buy_price) / req.p2p_buy_price * Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    # Dos piernas (compra + venta) pagan maker_fee_pct
    net_spread = (gross_spread - (req.maker_fee_pct * Decimal(2))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    fx_premium = ((req.p2p_buy_price - req.official_fx_rate) / req.official_fx_rate * Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    trap_flags: list[str] = []
    risk_score = 0

    if req.min_order_limit_fiat <= Decimal(5):
        trap_flags.append("TRAP_MICRO_LIMIT: Límite mínimo <= 5 unidades diseñado para atrapar bots de repricing.")
        risk_score += 40

    if abs(fx_premium) > Decimal("5.00"):
        trap_flags.append(f"OFF_MARKET_ANOMALY: Desviación de {fx_premium}% respecto al FX oficial.")
        risk_score += 30

    if req.advertiser_completion_rate_pct < Decimal("95.0") or req.advertiser_orders_30d < 30:
        trap_flags.append("LOW_REPUTATION_COUNTERPARTY: Tasa de cierre < 95% o historial < 30 órdenes/30d.")
        risk_score += 30

    risk_score = min(100, risk_score)
    if risk_score >= 50:
        rec = "REJECT_ADVERTISER: Alto riesgo de anuncio trampa o fraude por triangulación bancaria."
    elif net_spread <= Decimal("0.00"):
        rec = "NO_ARBITRAGE: Spread neto negativo o nulo tras comisiones."
    else:
        rec = f"VIABLE_SPREAD: Margen neto positivo de {net_spread}% sujeto a verificación KYC manual antes de liberar."

    return LatamP2PIntelResponse(
        fiat_currency=req.fiat_currency,
        payment_rail=req.payment_rail,
        gross_spread_pct=str(gross_spread),
        net_spread_pct=str(net_spread),
        fx_premium_vs_official_pct=str(fx_premium),
        counterparty_risk_score=risk_score,
        trap_ad_flags=trap_flags,
        recommendation=rec,
    )


# ==============================================================================
# TOOL #73: CONCILIATE CRYPTO TAX LOT (FIFO Fiscal LATAM)
# ==============================================================================


class TaxTradeLot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    side: Literal["BUY", "SELL"]
    quantity: Decimal = Field(..., gt=0)
    unit_price_usd: Decimal = Field(..., gt=0)
    official_fx_rate: Decimal = Field(..., gt=0, description="Tipo de cambio oficial del día hacia moneda local")
    fee_usd: Decimal = Field(default=Decimal("0.00"), ge=0)


class CryptoTaxConciliationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset: str = Field(..., min_length=2, max_length=12)
    local_currency: Literal["PEN", "COP", "MXN", "ARS", "BRL"] = "PEN"
    trades: list[TaxTradeLot] = Field(..., min_length=1, max_length=500)


class CryptoTaxConciliationResponse(BaseModel):
    asset: str
    local_currency: str
    method: str
    realized_pnl_usd: str
    realized_pnl_local: str
    remaining_quantity: str
    remaining_cost_basis_usd: str
    audit_digest_sha256: str


def conciliate_crypto_tax_lot(req: CryptoTaxConciliationRequest) -> CryptoTaxConciliationResponse:
    """Tool #73: Concilia lotes de compra/venta bajo método FIFO en USD y moneda local oficial."""
    fifo_queue: list[list[Decimal]] = []  # [remaining_qty, unit_cost_usd_incl_fee]
    realized_pnl_usd = Decimal("0.00")
    realized_pnl_local = Decimal("0.00")

    for trade in req.trades:
        if trade.side == "BUY":
            effective_unit_cost = ((trade.quantity * trade.unit_price_usd) + trade.fee_usd) / trade.quantity
            fifo_queue.append([trade.quantity, effective_unit_cost])
        else:
            qty_to_sell = trade.quantity
            proceeds_per_unit = ((trade.quantity * trade.unit_price_usd) - trade.fee_usd) / trade.quantity
            while qty_to_sell > Decimal(0) and fifo_queue:
                lot_qty, lot_cost = fifo_queue[0]
                matched = min(qty_to_sell, lot_qty)
                pnl_usd = (proceeds_per_unit - lot_cost) * matched
                realized_pnl_usd += pnl_usd
                realized_pnl_local += pnl_usd * trade.official_fx_rate
                lot_qty -= matched
                qty_to_sell -= matched
                if lot_qty == Decimal(0):
                    fifo_queue.pop(0)
                else:
                    fifo_queue[0][0] = lot_qty
            if qty_to_sell > Decimal(0):
                raise ValueError(f"Venta de {req.asset} excede el inventario FIFO disponible por {qty_to_sell} unidades.")

    rem_qty = sum((lot[0] for lot in fifo_queue), Decimal(0))
    rem_cost = sum((lot[0] * lot[1] for lot in fifo_queue), Decimal(0))

    digest_payload = f"{req.asset}:{req.local_currency}:{realized_pnl_usd}:{rem_qty}:{len(req.trades)}"
    audit_digest = hashlib.sha256(digest_payload.encode("utf-8")).hexdigest()

    return CryptoTaxConciliationResponse(
        asset=req.asset,
        local_currency=req.local_currency,
        method="FIFO",
        realized_pnl_usd=str(realized_pnl_usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        realized_pnl_local=str(realized_pnl_local.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        remaining_quantity=str(rem_qty.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)),
        remaining_cost_basis_usd=str(rem_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        audit_digest_sha256=audit_digest,
    )
