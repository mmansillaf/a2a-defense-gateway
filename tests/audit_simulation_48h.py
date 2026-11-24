"""
Auditoría y Simulación Empírica de Seguridad, Lógica y Cálculos (Últimas 48 Horas).
Ecosistema A2A Defense Gateway & Herramientas #46 a #50.
"""

import json
import time
from decimal import Decimal

import requests
from ap2_and_geo_suite import (
    CartItem,
    CartMandateInput,
    verify_ap2_cart_mandate_integrity,
)
from trading_risk_envelope import (
    CircuitBreakerRequest,
    MEVSimulationRequest,
    OrderSide,
    TradeProposalRequest,
    enforce_trading_circuit_breaker,
    propose_trade_envelope,
    simulate_order_mev_protection,
)


def run_audit_suite():
    results = {
        "timestamp": time.time(),
        "tests_executed": 0,
        "tests_passed": 0,
        "failures": [],
        "benchmarks": {},
        "production_probes": {},
    }

    print("=== INICIANDO SIMULACIONES Y PRUEBAS EMPÍRICAS DE AUDITORÍA ===")

    # --------------------------------------------------------------------------
    # 1. LÓGICA & SEGURIDAD FINANCIERA: TOOL #48 (propose_trade_envelope)
    # --------------------------------------------------------------------------
    t0 = time.perf_counter()
    # Test 1.1: Whitelist Enforcement
    try:
        results["tests_executed"] += 1
        propose_trade_envelope(TradeProposalRequest(
            symbol="MALICIOUS_COIN",
            side=OrderSide.BUY,
            quote_amount_usd=Decimal("10.00"),
        ))
        results["failures"].append("Tool 48 falló al permitir token no autorizado en whitelist")
    except ValueError:
        results["tests_passed"] += 1

    # Test 1.2: Hard Limit Cap Enforcement ($500 USD)
    try:
        results["tests_executed"] += 1
        propose_trade_envelope(TradeProposalRequest(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quote_amount_usd=Decimal("500.01"),
        ))
        results["failures"].append("Tool 48 falló al permitir orden > $500 USD")
    except ValueError:
        results["tests_passed"] += 1

    # Test 1.3: Slippage BPS Boundary Enforcement
    try:
        results["tests_executed"] += 1
        propose_trade_envelope(TradeProposalRequest(
            symbol="ETHUSDT",
            side=OrderSide.BUY,
            quote_amount_usd=Decimal("100.00"),
            max_slippage_bps=51,
        ))
        results["failures"].append("Tool 48 falló al permitir slippage > 50 bps")
    except ValueError:
        results["tests_passed"] += 1

    # Test 1.4: HITL Mandatory Flagging for orders >= $250
    results["tests_executed"] += 1
    resp_hitl = propose_trade_envelope(TradeProposalRequest(
        symbol="SOLUSDT",
        side=OrderSide.BUY,
        quote_amount_usd=Decimal("250.00"),
    ))
    if resp_hitl.requires_hitl and resp_hitl.state == "awaiting_human_approval":
        results["tests_passed"] += 1
    else:
        results["failures"].append("Tool 48 falló al marcar HITL obligatorio para orden >= $250 USD")

    # Test 1.5: Precision decimal en cantidad estimada
    results["tests_executed"] += 1
    resp_prec = propose_trade_envelope(TradeProposalRequest(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quote_amount_usd=Decimal("100.00"),
    ))
    # 100 / 96000 = 0.001041666... -> 0.00104167
    expected_qty = (Decimal("100.00") / Decimal("96000.00")).quantize(Decimal("0.00000001"))
    if Decimal(resp_prec.estimated_quantity) == expected_qty:
        results["tests_passed"] += 1
    else:
        results["failures"].append(f"Discrepancia aritmética: {resp_prec.estimated_quantity} != {expected_qty}")

    results["benchmarks"]["tool_48_latency_ms"] = (time.perf_counter() - t0) * 1000

    # --------------------------------------------------------------------------
    # 2. SIMULACIÓN PRE-FLIGHT ANTI-MEV: TOOL #49 (simulate_order_mev_protection)
    # --------------------------------------------------------------------------
    t0 = time.perf_counter()
    # Test 2.1: Sandwich Attack Risk en Mempool Público
    results["tests_executed"] += 1
    mev_vuln = simulate_order_mev_protection(MEVSimulationRequest(
        symbol="ETHUSDT",
        quote_amount_usd=Decimal("450.00"),
        mempool_type="public",
    ))
    if mev_vuln.sandwich_vulnerability and mev_vuln.mev_risk_score >= 0.70 and "Jito" in mev_vuln.recommended_routing:
        results["tests_passed"] += 1
    else:
        results["failures"].append("Tool 49 no detectó vulnerabilidad sándwich en mempool público")

    # Test 2.2: Honeypot & Transfer Tax Detection
    results["tests_executed"] += 1
    mev_scam = simulate_order_mev_protection(MEVSimulationRequest(
        symbol="SCAM_HONEY_TOKEN",
        quote_amount_usd=Decimal("50.00"),
    ))
    if mev_scam.is_honeypot and mev_scam.sell_tax_pct > 90.0 and mev_scam.mev_risk_score == 1.0:
        results["tests_passed"] += 1
    else:
        results["failures"].append("Tool 49 no detectó trampa de liquidez Honeypot")

    results["benchmarks"]["tool_49_latency_ms"] = (time.perf_counter() - t0) * 1000

    # --------------------------------------------------------------------------
    # 3. CIRCUIT BREAKER DE TESORERÍA: TOOL #50 (enforce_trading_circuit_breaker)
    # --------------------------------------------------------------------------
    t0 = time.perf_counter()
    # Test 3.1: Trigger por Drawdown Crítico (> 5%)
    results["tests_executed"] += 1
    cb_trip = enforce_trading_circuit_breaker(CircuitBreakerRequest(
        agent_id="adversarial_bot_01",
        rolling_24h_drawdown_pct=5.4,
        consecutive_loss_count=1,
    ))
    if cb_trip.circuit_breaker_status == "TRIPPED_LOCKED" and cb_trip.execution_halted and cb_trip.incident_hash:
        results["tests_passed"] += 1
    else:
        results["failures"].append("Tool 50 falló al disparar circuit breaker ante drawdown > 5%")

    # Test 3.2: Trigger por Racha de Pérdidas (>= 3)
    results["tests_executed"] += 1
    cb_streak = enforce_trading_circuit_breaker(CircuitBreakerRequest(
        agent_id="adversarial_bot_02",
        rolling_24h_drawdown_pct=1.2,
        consecutive_loss_count=3,
    ))
    if cb_streak.circuit_breaker_status == "TRIPPED_LOCKED" and cb_streak.execution_halted:
        results["tests_passed"] += 1
    else:
        results["failures"].append("Tool 50 falló al disparar circuit breaker ante racha de 3 pérdidas")

    results["benchmarks"]["tool_50_latency_ms"] = (time.perf_counter() - t0) * 1000

    # --------------------------------------------------------------------------
    # 4. MANDATOS AP2 & CATALOG GEO: TOOLS #46 Y #47
    # --------------------------------------------------------------------------
    t0 = time.perf_counter()
    # Test 4.1: Detección de Manipulación en Hash Canónico de Carrito AP2
    results["tests_executed"] += 1
    items = [CartItem(item_id="i1", sku="SKU-A", name="Widget", unit_price=20.0, quantity=2)]
    ap2_valid = verify_ap2_cart_mandate_integrity(CartMandateInput(
        mandate_id="man_001",
        cart_items=items,
        expected_total=40.0,
        spending_limit=50.0,
    ))
    # Alterar hash canónico
    ap2_tampered = verify_ap2_cart_mandate_integrity(CartMandateInput(
        mandate_id="man_001",
        cart_items=items,
        expected_total=40.0,
        spending_limit=50.0,
        cart_state_hash="tampered_hash_00000000000000000000000000000000",
    ))
    if ap2_valid.status == "VERIFIED" and ap2_tampered.tampering_detected and "TAMPERING_DETECTED" in str(ap2_tampered.reasons):
        results["tests_passed"] += 1
    else:
        results["failures"].append("Tool 46 no detectó alteración en hash canónico de carrito AP2")

    results["benchmarks"]["tool_46_latency_ms"] = (time.perf_counter() - t0) * 1000

    # --------------------------------------------------------------------------
    # 5. TELEMETRÍA REMOTA EN PRODUCCIÓN (VPS Contabo 167.86.108.85)
    # --------------------------------------------------------------------------
    print("Verificando endpoints en producción pública (https://a2a.vilmamonroy.com)...")
    try:
        t_health = time.perf_counter()
        r_health = requests.get("https://a2a.vilmamonroy.com/health", timeout=10)
        results["benchmarks"]["prod_health_latency_ms"] = (time.perf_counter() - t_health) * 1000
        results["production_probes"]["health_status"] = r_health.status_code
        results["production_probes"]["health_json"] = r_health.json()

        t_card = time.perf_counter()
        r_card = requests.get("https://a2a.vilmamonroy.com/.well-known/agent-card.json", timeout=10)
        results["benchmarks"]["prod_agent_card_latency_ms"] = (time.perf_counter() - t_card) * 1000
        results["production_probes"]["card_status"] = r_card.status_code
        card_data = r_card.json()
        results["production_probes"]["total_skills_exported"] = len(card_data.get("skills", []))

        # Probe live MCP invocation
        t_mcp = time.perf_counter()
        r_mcp = requests.post(
            "https://a2a.vilmamonroy.com/mcp",
            json={"jsonrpc": "2.0", "id": 999, "method": "tools/call", "params": {"name": "propose_trade_envelope", "arguments": {"symbol": "ETHUSDT", "side": "buy", "quote_amount_usd": 75.0}}},
            timeout=10,
        )
        results["benchmarks"]["prod_mcp_call_latency_ms"] = (time.perf_counter() - t_mcp) * 1000
        results["production_probes"]["mcp_call_status"] = r_mcp.status_code
        results["production_probes"]["mcp_call_response"] = r_mcp.json()
    except Exception as exc:
        results["failures"].append(f"Error conectando a producción: {exc!s}")

    print(json.dumps(results, indent=2, default=str))
    return results


if __name__ == "__main__":
    run_audit_suite()
