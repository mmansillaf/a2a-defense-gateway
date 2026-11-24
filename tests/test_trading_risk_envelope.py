from decimal import Decimal

import pytest
from mcp_server import MoltbookMonetizationMCPServer
from trading_risk_envelope import (
    CircuitBreakerRequest,
    DEXProtocol,
    FinancialPolicyEngine,
    MEVSimulationRequest,
    OrderSide,
    TradeProposalRequest,
    enforce_trading_circuit_breaker,
    simulate_order_mev_protection,
)


def test_financial_policy_engine_approval():
    engine = FinancialPolicyEngine(max_trade_usd=Decimal("500.00"))
    req = TradeProposalRequest(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quote_amount_usd=Decimal("150.00"),
    )
    resp = engine.evaluate_proposal(req)
    assert resp.state == "approved_for_execution"
    assert resp.requires_hitl is False
    assert resp.policy_checks["within_max_trade_limit"] is True


def test_financial_policy_engine_hitl():
    engine = FinancialPolicyEngine(max_trade_usd=Decimal("500.00"))
    req = TradeProposalRequest(
        symbol="ETHUSDT",
        side=OrderSide.SELL,
        quote_amount_usd=Decimal("300.00"),
    )
    resp = engine.evaluate_proposal(req)
    assert resp.state == "awaiting_human_approval"
    assert resp.requires_hitl is True


def test_financial_policy_engine_rejected_symbol():
    engine = FinancialPolicyEngine()
    req = TradeProposalRequest(
        symbol="DOGEUSDT",
        side=OrderSide.BUY,
        quote_amount_usd=Decimal("50.00"),
    )
    with pytest.raises(ValueError, match="no permitido en la whitelist"):
        engine.evaluate_proposal(req)


def test_financial_policy_engine_rejected_limit():
    engine = FinancialPolicyEngine(max_trade_usd=Decimal("500.00"))
    req = TradeProposalRequest(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quote_amount_usd=Decimal("999.00"),
    )
    with pytest.raises(ValueError, match="excede límite permitido"):
        engine.evaluate_proposal(req)


def test_financial_policy_engine_rejected_slippage():
    engine = FinancialPolicyEngine()
    req = TradeProposalRequest(
        symbol="SOLUSDT",
        side=OrderSide.BUY,
        quote_amount_usd=Decimal("100.00"),
        max_slippage_bps=120,
    )
    with pytest.raises(ValueError, match="Slippage solicitado"):
        engine.evaluate_proposal(req)


def test_simulate_order_mev_protection():
    # Safe low-volume trade
    safe_req = MEVSimulationRequest(
        symbol="ETHUSDT",
        dex_protocol=DEXProtocol.UNISWAP_V3,
        quote_amount_usd=Decimal("50.00"),
        mempool_type="public",
    )
    safe_res = simulate_order_mev_protection(safe_req)
    assert safe_res.sandwich_vulnerability is False
    assert safe_res.mev_risk_score < 0.5
    assert safe_res.is_honeypot is False

    # High-volume public trade (Sandwich vulnerability)
    vuln_req = MEVSimulationRequest(
        symbol="SOLUSDC",
        dex_protocol=DEXProtocol.RAYDIUM,
        quote_amount_usd=Decimal("500.00"),
        mempool_type="public",
    )
    vuln_res = simulate_order_mev_protection(vuln_req)
    assert vuln_res.sandwich_vulnerability is True
    assert "Jito" in vuln_res.recommended_routing or "Flashbots" in vuln_res.recommended_routing

    # Honeypot detection
    scam_req = MEVSimulationRequest(
        symbol="SCAM_TOKEN_ETH",
        quote_amount_usd=Decimal("100.00"),
    )
    scam_res = simulate_order_mev_protection(scam_req)
    assert scam_res.is_honeypot is True
    assert scam_res.sell_tax_pct > 50.0
    assert scam_res.mev_risk_score == 1.0


def test_enforce_trading_circuit_breaker():
    # Healthy status
    healthy_req = CircuitBreakerRequest(
        agent_id="agent_alpha",
        rolling_24h_drawdown_pct=2.1,
        consecutive_loss_count=1,
    )
    healthy_res = enforce_trading_circuit_breaker(healthy_req)
    assert healthy_res.circuit_breaker_status == "ARMED_HEALTHY"
    assert healthy_res.execution_halted is False

    # Tripped by drawdown
    drawdown_req = CircuitBreakerRequest(
        agent_id="agent_alpha",
        rolling_24h_drawdown_pct=6.5,
        consecutive_loss_count=1,
    )
    drawdown_res = enforce_trading_circuit_breaker(drawdown_req)
    assert drawdown_res.circuit_breaker_status == "TRIPPED_LOCKED"
    assert drawdown_res.execution_halted is True
    assert drawdown_res.incident_hash is not None

    # Tripped by consecutive losses
    streak_req = CircuitBreakerRequest(
        agent_id="agent_beta",
        rolling_24h_drawdown_pct=1.0,
        consecutive_loss_count=4,
    )
    streak_res = enforce_trading_circuit_breaker(streak_req)
    assert streak_res.circuit_breaker_status == "TRIPPED_LOCKED"
    assert streak_res.execution_halted is True


def test_mcp_server_dispatches_tools_48_49_50():
    server = MoltbookMonetizationMCPServer()
    assert len(server.list_tools()) == 69

    # Test Tool #48 via call_tool
    res48 = server.call_tool(
        "propose_trade_envelope",
        {"symbol": "BTCUSDT", "side": "buy", "quote_amount_usd": 120.0},
    )
    assert res48["state"] == "approved_for_execution"
    assert res48["symbol"] == "BTCUSDT"

    # Test Tool #49 via call_tool
    res49 = server.call_tool(
        "simulate_order_mev_protection",
        {"symbol": "ETHUSDT", "quote_amount_usd": 300.0, "mempool_type": "public"},
    )
    assert "simulation_id" in res49
    assert res49["sandwich_vulnerability"] is True

    # Test Tool #50 via call_tool
    res50 = server.call_tool(
        "enforce_trading_circuit_breaker",
        {"agent_id": "agent_test_50", "rolling_24h_drawdown_pct": 7.2, "consecutive_loss_count": 0},
    )
    assert res50["circuit_breaker_status"] == "TRIPPED_LOCKED"
    assert res50["execution_halted"] is True
