from pathlib import Path

from crypto_audit_log import MultiCaMeLLedger


def test_camel_ledger_creates_tamper_evident_chain(tmp_path: Path):
    ledger_path = tmp_path / "why_trail.jsonl"
    ledger = MultiCaMeLLedger(ledger_file=ledger_path)

    # 1. Registrar 3 eventos sucesivos
    e0 = ledger.record_event(
        event_type="SESSION_START",
        payload_data={"session_id": "sess_12345", "operator": "antigravity"},
        actor_agent_id="control_orchestrator",
    )
    e1 = ledger.record_event(
        event_type="INGESTION_QUARANTINE",
        payload_data={"post_id": "post_001", "threat_flag": False},
        actor_agent_id="quarantine_worker",
    )
    e2 = ledger.record_event(
        event_type="EPISTEMIC_ATTESTATION",
        payload_data={
            "claim_id": "CLM-0001",
            "sc_score": 0.88,
            "verdict": "VERIFIED_HIGH",
        },
        actor_agent_id="oracle_service",
    )

    assert len(ledger.chain) == 3
    assert e0.previous_block_hash == "0" * 64
    assert e1.previous_block_hash == e0.block_hash
    assert e2.previous_block_hash == e1.block_hash

    # 2. Verificar integridad matemática
    is_valid, err = ledger.verify_chain_integrity()
    assert is_valid is True
    assert err is None

    # 3. Simular intento de manipulación maliciosa de memoria (Tampering en bloque 1)
    tampered_entry = ledger.chain[1].model_copy(update={"payload_hash": "a" * 64})
    ledger.chain[1] = tampered_entry

    is_valid_tampered, tamper_err = ledger.verify_chain_integrity()
    assert is_valid_tampered is False
    assert "Firma corrupta en bloque 1" in tamper_err

    # 4. Probar persistencia y rehidratación desde disco
    clean_ledger = MultiCaMeLLedger(ledger_file=tmp_path / "fresh.jsonl")
    clean_ledger.record_event("EVENT_A", {"data": 1}, "agent_a")
    clean_ledger.record_event("EVENT_B", {"data": 2}, "agent_b")

    reloaded = MultiCaMeLLedger(ledger_file=tmp_path / "fresh.jsonl")
    assert len(reloaded.chain) == 2
    assert reloaded.verify_chain_integrity()[0] is True

    # 5. Probar filtrado por agente
    agent_a_trail = reloaded.get_audit_trail_for_actor("agent_a")
    assert len(agent_a_trail) == 1
    assert agent_a_trail[0].event_type == "EVENT_A"


def test_mcp_server_and_api_gateway_auto_audits_interactions(tmp_path: Path):
    from api_gateway import app, server
    from fastapi.testclient import TestClient

    ledger_path = tmp_path / "gateway_audit.jsonl"
    server.ledger = MultiCaMeLLedger(ledger_file=ledger_path)

    client = TestClient(app)

    # 1. Llamar a herramienta vía HTTP POST
    res = client.post(
        "/api/v1/tools/call",
        json={"name": "calculate_service_quote", "arguments": {"service_type": "standard_audit"}},
        headers={"x-agent-id": "autonomous_agent_42"},
    )
    assert res.status_code == 200

    # 2. Consultar feed
    res_feed = client.get("/api/v1/alpha-feed", headers={"x-agent-id": "scout_agent_99"})
    assert res_feed.status_code == 200

    # 3. Verificar que el ledger registró eventos HTTP y Tool Calls
    assert len(server.ledger.chain) >= 2
    assert ledger_path.exists()

    # 4. Verificar integridad matemática de la cadena generada
    res_verify = client.get("/api/v1/audit/verify")
    assert res_verify.status_code == 200
    assert res_verify.json()["status"] == "VALID"

    # 5. Verificar consulta del trail
    res_trail = client.get("/api/v1/audit/trail?limit=10")
    assert res_trail.status_code == 200
    assert res_trail.json()["total_entries"] >= 2
