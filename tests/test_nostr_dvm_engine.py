import nostr_sdk as ns
import pytest

from scripts.nostr_dvm_engine import DVM_COMPUTE_REQUEST_KIND, NostrDVMEngine


@pytest.fixture
def dvm_engine():
    return NostrDVMEngine()


def test_dvm_initialization(dvm_engine):
    assert dvm_engine.npub.startswith("npub1")
    assert len(dvm_engine.pubkey_hex) == 64


def test_dvm_simulation_flow(dvm_engine):
    res = dvm_engine.simulate_job_flow(test_code="print('Nostr test 42')")
    assert res["simulation_status"] == "SUCCESS"
    assert res["status"] == "SUCCESS"
    assert "Nostr test 42" in res["output_preview"]
    assert res["latency_ms"] > 0
    assert res["cryptographic_verification"] is True


def test_dvm_security_ast_blocking(dvm_engine):
    customer_keys = ns.Keys.generate()
    malicious_code = "import os; os.system('cat /etc/passwd')"

    req_tags = [
        ns.Tag.parse(["p", dvm_engine.pubkey_hex]),
        ns.Tag.parse(["i", malicious_code, "text"]),
        ns.Tag.parse(["param", "tool", "execute_sandboxed_computation"]),
        ns.Tag.parse(["bid", "100"]),
    ]
    req_builder = ns.EventBuilder(ns.Kind(DVM_COMPUTE_REQUEST_KIND), malicious_code).tags(req_tags)
    req_event = req_builder.finalize(customer_keys)

    parsed_req = dvm_engine.parse_job_request(req_event)
    res = dvm_engine.process_job(parsed_req)

    assert res.status == "REJECTED_SECURITY"
    assert "SECURITY REJECTED (AST SAST)" in res.output
    assert res.latency_ms > 0
