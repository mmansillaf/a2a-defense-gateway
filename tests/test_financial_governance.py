from financial_policy_proxy import (
    FinancialPolicyProxy,
    PolicyConfig,
    ProxyPaymentIntent,
    SagaStep,
)


def get_test_proxy(tmp_path) -> FinancialPolicyProxy:
    db_file = str(tmp_path / "test_payment_audit.db")
    config = PolicyConfig(
        max_per_tx_usd=0.25,
        max_per_hour_usd=2.00,
        max_per_day_usd=10.00,
        hitl_threshold_usd=1.00,
        max_consecutive_errors=3,
        allowlist_domains=["127.0.0.1", "localhost", "api.proveedor-verificado.com", "a2a.vilmamonroy.com"],
    )
    return FinancialPolicyProxy(config=config, db_path=db_file)


def test_fin_01_blocks_unauthorized_domain(tmp_path):
    proxy = get_test_proxy(tmp_path)
    intent = ProxyPaymentIntent(
        agent_id="agent-rogue-01",
        target_url="https://evil-exfiltrator.io/drain-wallet",
        amount_usd=0.10,
        payload={"command": "transfer_funds"},
    )
    res = proxy.evaluate_payment_intent(intent)
    assert res.decision == "BLOCKED"
    assert res.status_code == 403
    assert "FIN-01" in res.reason
    assert "evil-exfiltrator.io" in res.reason

    summary = proxy.get_audit_summary("agent-rogue-01")
    assert summary["status_breakdown"]["BLOCKED"]["count"] == 1


def test_fin_02_circuit_breaker_trips_after_failures(tmp_path):
    proxy = get_test_proxy(tmp_path)
    target = "https://api.proveedor-verificado.com/v1/compute"

    # Simular 3 fallos consecutivos post-pago
    for _ in range(3):
        proxy.record_payment_result(
            agent_id="agent-01",
            target_url=target,
            amount_usd=0.05,
            success=False,
            error_detail="Proveedor retornó HTTP 500 tras recibir pago",
        )

    # 4ta llamada: el circuit breaker debe bloquear antes de realizar ningún pago
    intent = ProxyPaymentIntent(
        agent_id="agent-01",
        target_url=target,
        amount_usd=0.05,
    )
    res = proxy.evaluate_payment_intent(intent)
    assert res.decision == "BLOCKED"
    assert res.status_code == 503
    assert res.circuit_tripped is True
    assert "FIN-02" in res.reason


def test_fin_03_hourly_and_daily_spending_caps(tmp_path):
    proxy = get_test_proxy(tmp_path)
    target = "https://api.proveedor-verificado.com/v1/search"

    # Simular $1.90 de gasto previo exitoso
    for i in range(19):
        proxy.record_payment_result(
            agent_id="agent-budget-cap",
            target_url=target,
            amount_usd=0.10,
            success=True,
            tx_hash=f"tx_{i}",
        )

    # Intento de gastar $0.15 adicionales (1.90 + 0.15 = 2.05 > 2.00 límite horario)
    intent = ProxyPaymentIntent(
        agent_id="agent-budget-cap",
        target_url=target,
        amount_usd=0.15,
    )
    res = proxy.evaluate_payment_intent(intent)
    assert res.decision == "BLOCKED"
    assert res.status_code == 429
    assert "FIN-03" in res.reason
    assert "Presupuesto por hora agotado" in res.reason


def test_fin_04_price_spikes_and_hitl_threshold(tmp_path):
    proxy = get_test_proxy(tmp_path)
    target = "https://api.proveedor-verificado.com/v1/search"

    # Caso A: $0.50 supera max_per_tx_usd ($0.25) pero es menor a HITL ($1.00) -> 403
    intent_tx = ProxyPaymentIntent(
        agent_id="agent-02",
        target_url=target,
        amount_usd=0.50,
    )
    res_tx = proxy.evaluate_payment_intent(intent_tx)
    assert res_tx.decision == "BLOCKED"
    assert res_tx.status_code == 403
    assert "límite máximo por transacción" in res_tx.reason

    # Caso B: $1.50 supera el umbral HITL ($1.00) -> 202 PENDING_HITL
    intent_hitl = ProxyPaymentIntent(
        agent_id="agent-02",
        target_url=target,
        amount_usd=1.50,
    )
    res_hitl = proxy.evaluate_payment_intent(intent_hitl)
    assert res_hitl.decision == "PENDING_HITL"
    assert res_hitl.status_code == 202
    assert "FIN-04" in res_hitl.reason
    assert "requiere aprobación humana" in res_hitl.reason.lower() or "hitl" in res_hitl.reason.lower()


def test_fin_05_malformed_402_challenge_rejection(tmp_path):
    proxy = get_test_proxy(tmp_path)
    target = "https://api.proveedor-verificado.com/v1/search"

    # Reto malformado (JSON corrupto)
    intent_corrupt = ProxyPaymentIntent(
        agent_id="agent-03",
        target_url=target,
        amount_usd=0.10,
        challenge_headers={"X-PAYMENT-REQUIRED": "{malformed-json-payload"},
    )
    res_corrupt = proxy.evaluate_payment_intent(intent_corrupt)
    assert res_corrupt.decision == "ERROR"
    assert res_corrupt.status_code == 502
    assert "FIN-05" in res_corrupt.reason

    # Reto malformado (falta amount_usd)
    intent_missing = ProxyPaymentIntent(
        agent_id="agent-03",
        target_url=target,
        amount_usd=0.10,
        challenge_headers={"X-PAYMENT-REQUIRED": '{"currency": "USDC"}'},
    )
    res_missing = proxy.evaluate_payment_intent(intent_missing)
    assert res_missing.decision == "ERROR"
    assert res_missing.status_code == 502


def test_m2m_saga_orchestration_success_and_compensation(tmp_path):
    proxy = get_test_proxy(tmp_path)

    # 1. Saga exitosa de 3 pasos
    steps_ok = [
        SagaStep(step_id="S1", agent_id="agent_indexer", service_name="data_indexing", action_type="EXECUTE", cost_usd=0.10),
        SagaStep(step_id="S2", agent_id="agent_classifier", service_name="nlp_classification", action_type="EXECUTE", cost_usd=0.15),
        SagaStep(step_id="S3", agent_id="agent_notifier", service_name="webhook_dispatch", action_type="EXECUTE", cost_usd=0.05),
    ]
    res_ok = proxy.orchestrate_saga(saga_id="SAGA-2026-OK", steps=steps_ok)
    assert res_ok.status == "COMPLETED"
    assert res_ok.steps_executed == 3
    assert res_ok.steps_compensated == 0
    assert abs(res_ok.total_cost_usd - 0.30) < 1e-4

    # 2. Saga con fallo en el paso 3 que desencadena compensación reversa de los pasos 2 y 1
    steps_fail = [
        SagaStep(step_id="P1", agent_id="agent_escrow", service_name="lock_funds", action_type="EXECUTE", cost_usd=0.20),
        SagaStep(step_id="P2", agent_id="agent_gpu", service_name="reserve_compute", action_type="EXECUTE", cost_usd=0.50),
        SagaStep(
            step_id="P3",
            agent_id="agent_storage",
            service_name="commit_payload",
            action_type="EXECUTE",
            payload={"simulate_failure": True, "failure_reason": "Storage quota exceeded on agent host"},
            cost_usd=0.10,
        ),
    ]
    res_comp = proxy.orchestrate_saga(saga_id="SAGA-2026-COMP", steps=steps_fail)
    assert res_comp.status == "COMPENSATED"
    assert res_comp.steps_executed == 2
    assert res_comp.steps_compensated == 2
    assert res_comp.total_cost_usd == 0.0
    assert "Storage quota exceeded" in res_comp.error_detail
