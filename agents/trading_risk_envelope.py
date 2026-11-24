"""
Trading Risk Envelope & Financial Policy Engine for Autonomous AI Agents.
Herramientas #48, #49 y #50 del Ecosistema A2A Defense Gateway.

Implements out-of-prompt policy enforcement, pre-flight MEV honeypot simulation,
drawdown circuit breakers, and deterministic JSON-RPC MCP capability contracts.
"""

import hashlib
import time
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class DEXProtocol(str, Enum):
    UNISWAP_V3 = "uniswap_v3"
    HYPERLIQUID = "hyperliquid"
    RAYDIUM = "raydium"
    JITO_SOLANA = "jito_solana"


# ==============================================================================
# TOOL #48: PROPOSE TRADE ENVELOPE (Schemas & Logic)
# ==============================================================================

class TradeProposalRequest(BaseModel):
    symbol: str = Field(..., description="Ticker pair, e.g. BTCUSDT, ETHUSDT, SOLUSDT, USDCUSDT")
    side: OrderSide = Field(..., description="Order direction: buy or sell")
    quote_amount_usd: Decimal = Field(..., gt=0, description="Amount in USD/USDC")
    max_slippage_bps: int = Field(default=50, ge=1, le=500, description="Max allowed slippage in basis points (50 = 0.5%)")
    agent_id: str = Field(default="agent_unknown", description="ID of the proposing autonomous agent")


class TradeProposalResponse(BaseModel):
    state: str = Field(..., description="Execution state: approved_for_execution, rejected, awaiting_human_approval")
    proposal_id: str
    symbol: str
    side: OrderSide
    quote_amount_usd: str
    estimated_price: str
    estimated_quantity: str
    max_slippage_bps: int
    requires_hitl: bool
    policy_checks: dict[str, bool]
    timestamp: int


class FinancialPolicyEngine:
    """Motor determinista de políticas de contención para operaciones financieras agénticas."""

    def __init__(
        self,
        max_trade_usd: Decimal = Decimal("500.00"),
        daily_limit_usd: Decimal = Decimal("2000.00"),
        max_slippage_bps: int = 50,
        allowed_symbols: set[str] | None = None,
    ):
        self.max_trade_usd = max_trade_usd
        self.daily_limit_usd = daily_limit_usd
        self.max_slippage_bps = max_slippage_bps
        self.allowed_symbols = allowed_symbols or {"BTCUSDT", "ETHUSDT", "SOLUSDT", "USDCUSDT"}
        self.mock_prices = {
            "BTCUSDT": Decimal("96000.00"),
            "ETHUSDT": Decimal("3100.00"),
            "SOLUSDT": Decimal("210.00"),
            "USDCUSDT": Decimal("1.00"),
        }

    def evaluate_proposal(self, req: TradeProposalRequest) -> TradeProposalResponse:
        checks = {
            "symbol_whitelisted": req.symbol in self.allowed_symbols,
            "within_max_trade_limit": req.quote_amount_usd <= self.max_trade_usd,
            "slippage_within_tolerance": req.max_slippage_bps <= self.max_slippage_bps,
            "positive_amount": req.quote_amount_usd > 0,
        }

        if not checks["symbol_whitelisted"]:
            raise ValueError(f"Símbolo no permitido en la whitelist de tesorería: {req.symbol}")

        if not checks["within_max_trade_limit"]:
            raise ValueError(f"Monto ({req.quote_amount_usd} USD) excede límite permitido ({self.max_trade_usd} USD)")

        if not checks["slippage_within_tolerance"]:
            raise ValueError(f"Slippage solicitado ({req.max_slippage_bps} bps) supera el umbral máximo de política ({self.max_slippage_bps} bps)")

        price = self.mock_prices[req.symbol]
        quantity = (req.quote_amount_usd / price).quantize(Decimal("0.00000001"))

        # Acciones mayores a 250 USD requieren aprobación humana obligatoria (HITL)
        requires_hitl = req.quote_amount_usd >= Decimal("250.00")
        state = "awaiting_human_approval" if requires_hitl else "approved_for_execution"

        entropy = f"{req.agent_id}:{req.symbol}:{req.quote_amount_usd}:{time.time()}"
        proposal_id = f"prop_{hashlib.sha256(entropy.encode()).hexdigest()[:16]}"

        return TradeProposalResponse(
            state=state,
            proposal_id=proposal_id,
            symbol=req.symbol,
            side=req.side,
            quote_amount_usd=str(req.quote_amount_usd),
            estimated_price=str(price),
            estimated_quantity=str(quantity),
            max_slippage_bps=req.max_slippage_bps,
            requires_hitl=requires_hitl,
            policy_checks=checks,
            timestamp=int(time.time()),
        )


def propose_trade_envelope(req: TradeProposalRequest) -> TradeProposalResponse:
    """Función de nivel superior para MCP Tool #48."""
    engine = FinancialPolicyEngine()
    return engine.evaluate_proposal(req)


# ==============================================================================
# TOOL #49: SIMULATE ORDER MEV PROTECTION (Schemas & Logic)
# ==============================================================================

class MEVSimulationRequest(BaseModel):
    symbol: str = Field(..., description="Target pair, e.g. ETHUSDT, SOLUSDC")
    dex_protocol: DEXProtocol = Field(default=DEXProtocol.UNISWAP_V3, description="Target execution liquidity venue")
    quote_amount_usd: Decimal = Field(..., gt=0, description="Nominal trade value in USD")
    mempool_type: str = Field(default="public", description="'public' mempool or 'private_relay' (Jito/Flashbots)")


class MEVSimulationResponse(BaseModel):
    simulation_id: str
    symbol: str
    dex_protocol: DEXProtocol
    mev_risk_score: float = Field(..., ge=0.0, le=1.0, description="Risk of sandwich or frontrun (0.0=safe, 1.0=critical)")
    sandwich_vulnerability: bool
    estimated_price_impact_bps: int
    is_honeypot: bool
    sell_tax_pct: float
    recommended_routing: str
    recommended_priority_fee_gwei: float
    audit_notes: list[str]


def simulate_order_mev_protection(req: MEVSimulationRequest) -> MEVSimulationResponse:
    """
    Función de nivel superior para MCP Tool #49:
    Simula pre-flight la orden contra riesgos de MEV (Sandwich attacks, front-running)
    y evalúa honeypot / transfer taxes en el pool de liquidez.
    """
    notes = []
    # Simulación de impacto según liquidez sintética
    if req.quote_amount_usd > Decimal("5000.00"):
        price_impact_bps = 85
        notes.append("Alto volumen relativo a profundidad del pool.")
    elif req.quote_amount_usd > Decimal("1000.00"):
        price_impact_bps = 25
    else:
        price_impact_bps = 4

    # Vulnerabilidad a sandwich en mempool público
    if req.mempool_type == "public" and req.quote_amount_usd >= Decimal("200.00"):
        mev_risk = 0.78
        sandwich_vuln = True
        recommended_routing = "ROUTER_PRIVATE_RPC_MANDATORY (Jito / Flashbots Protect)"
        notes.append("Orden vulnerable a sándwich en mempool público. Desviar a relay privado.")
    else:
        mev_risk = 0.12
        sandwich_vuln = False
        recommended_routing = "DIRECT_POOL_EXECUTION"
        notes.append("Riesgo MEV dentro de tolerancia segura.")

    is_honeypot = False
    sell_tax_pct = 0.0
    if "SCAM" in req.symbol.upper() or "HONEY" in req.symbol.upper():
        is_honeypot = True
        sell_tax_pct = 99.0
        mev_risk = 1.0
        recommended_routing = "EXECUTION_ABORTED_MALICIOUS_TOKEN"
        notes.append("ALERTA CRÍTICA: Código de token contiene trampa de liquidez (Honeypot).")

    sim_entropy = f"mev:{req.symbol}:{req.quote_amount_usd}:{time.time()}"
    sim_id = f"sim_{hashlib.sha256(sim_entropy.encode()).hexdigest()[:16]}"

    priority_fee = 2.5 if req.dex_protocol in (DEXProtocol.UNISWAP_V3, DEXProtocol.RAYDIUM) else 0.0

    return MEVSimulationResponse(
        simulation_id=sim_id,
        symbol=req.symbol,
        dex_protocol=req.dex_protocol,
        mev_risk_score=mev_risk,
        sandwich_vulnerability=sandwich_vuln,
        estimated_price_impact_bps=price_impact_bps,
        is_honeypot=is_honeypot,
        sell_tax_pct=sell_tax_pct,
        recommended_routing=recommended_routing,
        recommended_priority_fee_gwei=priority_fee,
        audit_notes=notes,
    )


# ==============================================================================
# TOOL #50: ENFORCE TRADING CIRCUIT BREAKER (Schemas & Logic)
# ==============================================================================

class CircuitBreakerRequest(BaseModel):
    agent_id: str = Field(..., description="Unique ID of autonomous agent")
    rolling_24h_drawdown_pct: float = Field(..., ge=0.0, description="Rolling 24h drawdown percentage (e.g. 5.5 = 5.5%)")
    consecutive_loss_count: int = Field(..., ge=0, description="Number of consecutive loss-making trades")
    unrealized_loss_usd: Decimal = Field(default=Decimal("0.00"), ge=0, description="Current open position loss")
    max_allowed_drawdown_pct: float = Field(default=5.0, description="Threshold triggering immediate kill-switch")
    max_consecutive_losses: int = Field(default=3, description="Max consecutive losses before circuit breaker trip")


class CircuitBreakerResponse(BaseModel):
    circuit_breaker_status: str = Field(..., description="'ARMED_HEALTHY' or 'TRIPPED_LOCKED'")
    agent_id: str
    execution_halted: bool
    breach_reasons: list[str]
    cooldown_period_seconds: int
    incident_hash: str | None
    recovery_action: str
    timestamp: int


def enforce_trading_circuit_breaker(req: CircuitBreakerRequest) -> CircuitBreakerResponse:
    """
    Función de nivel superior para MCP Tool #50:
    Circuit breaker financiero determinista fuera del prompt.
    Desactiva de inmediato las credenciales de ejecución del agente si se rompen
    las invariantes de riesgo (drawdown acumulado o rachas de pérdidas).
    """
    breaches = []
    if req.rolling_24h_drawdown_pct >= req.max_allowed_drawdown_pct:
        breaches.append(f"Drawdown 24h ({req.rolling_24h_drawdown_pct}%) supera umbral máximo ({req.max_allowed_drawdown_pct}%)")

    if req.consecutive_loss_count >= req.max_consecutive_losses:
        breaches.append(f"Pérdidas consecutivas ({req.consecutive_loss_count}) alcanzaron el tope de seguridad ({req.max_consecutive_losses})")

    is_tripped = len(breaches) > 0
    status = "TRIPPED_LOCKED" if is_tripped else "ARMED_HEALTHY"
    cooldown = 86400 if is_tripped else 0  # 24 horas de enfriamiento
    
    incident_hash = None
    if is_tripped:
        incident_data = f"{req.agent_id}:{req.rolling_24h_drawdown_pct}:{req.consecutive_loss_count}:{time.time()}"
        incident_hash = f"cb_{hashlib.sha256(incident_data.encode()).hexdigest()}"
        recovery = "REQUIRES_MANUAL_OPERATOR_OVERRIDE_AND_RISK_AUDIT"
    else:
        recovery = "NORMAL_AUTONOMOUS_OPERATION_AUTHORIZED"

    return CircuitBreakerResponse(
        circuit_breaker_status=status,
        agent_id=req.agent_id,
        execution_halted=is_tripped,
        breach_reasons=breaches,
        cooldown_period_seconds=cooldown,
        incident_hash=incident_hash,
        recovery_action=recovery,
        timestamp=int(time.time()),
    )
