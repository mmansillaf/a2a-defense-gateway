import pytest
from escrow_manager import EscrowManager
from token_pricing_engine import TokenPricingEngine


@pytest.fixture
def pricing_engine():
    return TokenPricingEngine()


@pytest.fixture
def escrow_manager():
    return EscrowManager()


def test_pricing_engine_dynamic_rates(pricing_engine):
    # Caso A: Solicitud estándar de bajo riesgo
    q_low = pricing_engine.calculate_price(
        service_type="epistemic_audit",
        estimated_compute_ms=50,
        estimated_tokens=500,
        adversarial_risk_score=0.05,
    )
    assert q_low.base_credits == 10
    assert q_low.risk_surcharge == 0
    assert q_low.total_credits >= 10

    # Caso B: Solicitud con riesgo adversarial alto (sobrecargo disuasorio)
    q_high = pricing_engine.calculate_price(
        service_type="epistemic_audit",
        estimated_compute_ms=100,
        estimated_tokens=1000,
        adversarial_risk_score=0.90,
    )
    assert q_high.risk_surcharge > 0
    assert q_high.total_credits > q_low.total_credits


def test_escrow_deposit_and_release(escrow_manager):
    # Cliente deposita 20 créditos de tarifa, Proveedor deposita 50 de colateral
    c = escrow_manager.create_contract(
        client_id="agent_client_01",
        provider_id="agent_oracle_01",
        service_fee=20,
        provider_stake=50,
    )

    assert c.total_locked_credits == 70
    assert c.status == "LOCKED"
    assert escrow_manager.vault_total_locked == 70

    # Servicio completado con éxito
    c_released = escrow_manager.release_funds(c.contract_id, fulfillment_hash="hash_attestation_ok")
    assert c_released.status == "COMPLETED"
    assert escrow_manager.vault_total_locked == 0


def test_escrow_dispute_and_slashing(escrow_manager):
    c = escrow_manager.create_contract(
        client_id="agent_client_victim",
        provider_id="agent_oracle_rogue",
        service_fee=30,
        provider_stake=60,
    )

    # Cliente abre disputa por atestación falsificada
    c_disp = escrow_manager.dispute_contract(c.contract_id, reason="Atestación desmentida por RFC oficial.")
    assert c_disp.status == "DISPUTED"
    assert escrow_manager.vault_total_locked == 90

    # Tribunal determina slashing del proveedor
    c_slashed, settlement = escrow_manager.execute_slashing(
        c.contract_id, slash_reason="Tribunal confirmó falsedad factual: colateral confiscado."
    )

    assert c_slashed.status == "SLASHED"
    assert settlement["client_payout"] == 90  # 30 reembolso + 60 indemnización
    assert settlement["provider_payout"] == 0
    assert escrow_manager.vault_total_locked == 0


def test_escrow_conservation_invariant(escrow_manager):
    # Verificar ley de conservación: fondos bloqueados en bóveda == suma de contratos activos
    for i in range(10):
        escrow_manager.create_contract(f"c_{i}", f"p_{i}", service_fee=10, provider_stake=20)

    assert escrow_manager.vault_total_locked == 300

    active_sum = sum(
        c.total_locked_credits
        for c in escrow_manager.contracts.values()
        if c.status in ("LOCKED", "DISPUTED")
    )
    assert escrow_manager.vault_total_locked == active_sum
