"""
Unit and Integration Test Suite for Agent Work Settlement Suite.
Covers:
1. issue_verifiable_work_receipt
2. audit_agent_dependency_liveness
3. sanitize_delegated_task_payload
4. auto_refund_dormant_escrow
Both directly and via MoltbookMonetizationMCPServer.call_tool().
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from agent_work_settlement_suite import (
    DependencyLivenessInput,
    DormantEscrowRefundInput,
    SanitizeTaskInput,
    WorkReceiptInput,
    audit_agent_dependency_liveness,
    auto_refund_dormant_escrow,
    issue_verifiable_work_receipt,
    sanitize_delegated_task_payload,
)
from escrow_manager import EscrowManager
from mcp_server import MoltbookMonetizationMCPServer


@pytest.fixture
def mcp_server():
    return MoltbookMonetizationMCPServer()


# ============================================================================
# 1. Tests for issue_verifiable_work_receipt
# ============================================================================

def test_issue_verifiable_work_receipt_direct():
    inp = WorkReceiptInput(
        task_id="TASK-889900",
        client_agent_id="agent_alpha",
        provider_agent_id="agent_beta",
        input_payload="Generate contract analysis for NDA",
        output_payload="Contract analysis completed: No indemnification clause found.",
        settlement_credits=500,
        execution_latency_ms=124.5,
        signing_secret="TEST_SIGNING_SECRET_123",
        metadata={"jurisdiction": "US_DELAWARE"},
    )
    receipt = issue_verifiable_work_receipt(inp)

    assert receipt.receipt_id.startswith("RCP-")
    assert receipt.status == "ISSUED_AND_VERIFIABLE"
    assert receipt.task_id == "TASK-889900"
    assert receipt.client_agent_id == "agent_alpha"
    assert receipt.provider_agent_id == "agent_beta"
    assert receipt.settlement_credits == 500
    assert receipt.execution_latency_ms == 124.5
    assert len(receipt.input_sha256) == 64
    assert len(receipt.output_sha256) == 64
    assert len(receipt.hmac_sha256_signature) == 64
    assert receipt.rfc3161_compatible is True
    assert receipt.deductible_accounting_record["units"] == 500


def test_issue_verifiable_work_receipt_via_mcp(mcp_server):
    args = {
        "task_id": "TASK-101112",
        "client_agent_id": "client_99",
        "provider_agent_id": "provider_88",
        "input_payload": "SELECT * FROM legal_corpus WHERE court='scotus'",
        "output_payload": "Found 12 matching cases.",
        "settlement_credits": 120,
        "execution_latency_ms": 45.0,
    }
    res = mcp_server.call_tool("issue_verifiable_work_receipt", args)
    assert res["status"] == "ISSUED_AND_VERIFIABLE"
    assert res["task_id"] == "TASK-101112"
    assert "hmac_sha256_signature" in res


# ============================================================================
# 2. Tests for audit_agent_dependency_liveness
# ============================================================================

def test_audit_agent_dependency_liveness_simulated():
    # Test simulated alive
    inp_ok = DependencyLivenessInput(
        dependency_url="https://api.upstream-agent.internal/v1/health",
        mock_offline_simulate=False,
    )
    res_ok = audit_agent_dependency_liveness(inp_ok)
    assert res_ok.is_alive is True
    assert res_ok.verdict == "OPERATIONAL"
    assert res_ok.risk_for_escrow_locking == "SAFE"

    # Test simulated offline
    inp_fail = DependencyLivenessInput(
        dependency_url="https://api.upstream-agent.internal/v1/health",
        mock_offline_simulate=True,
    )
    res_fail = audit_agent_dependency_liveness(inp_fail)
    assert res_fail.is_alive is False
    assert res_fail.verdict == "UNREACHABLE"
    assert res_fail.risk_for_escrow_locking == "HIGH_RISK"
    assert res_fail.failure_reason == "SIMULATED_DEPENDENCY_OUTAGE"


def test_audit_agent_dependency_liveness_invalid_scheme():
    inp_invalid = DependencyLivenessInput(
        dependency_url="ftp://bad-scheme.com/resource",
    )
    res = audit_agent_dependency_liveness(inp_invalid)
    assert res.is_alive is False
    assert "INVALID_SCHEME" in (res.failure_reason or "")


def test_audit_agent_dependency_liveness_via_mcp(mcp_server):
    args = {
        "dependency_url": "https://service.peer.net/status",
        "mock_offline_simulate": False,
    }
    res = mcp_server.call_tool("audit_agent_dependency_liveness", args)
    assert res["is_alive"] is True
    assert res["verdict"] == "OPERATIONAL"


# ============================================================================
# 3. Tests for sanitize_delegated_task_payload
# ============================================================================

def test_sanitize_delegated_task_payload_with_secrets_and_pii():
    dirty_text = (
        "Here is my prompt. Call OpenAI using sk-abcdef1234567890abcdef1234567890. "
        "Also my AWS key is AKIAIOSFODNN7EXAMPLE and GitHub token is "
        "ghp_1234567890abcdefghijklmnopqrstuvwxyz12. "
        "Contact me at alice.infiltrator@example.com or use card 4111111111111111."
    )
    inp = SanitizeTaskInput(payload_text=dirty_text)
    res = sanitize_delegated_task_payload(inp)

    assert res.leak_prevented is True
    assert res.safety_verdict == "SANITIZED_SECRETS_STRIPPED"
    assert res.redactions_count >= 5
    assert "sk-" not in res.sanitized_payload
    assert "AKIAIOSFODNN7EXAMPLE" not in res.sanitized_payload
    assert "ghp_" not in res.sanitized_payload
    assert "alice.infiltrator@example.com" not in res.sanitized_payload
    assert "4111111111111111" not in res.sanitized_payload


def test_sanitize_delegated_task_payload_clean():
    clean_text = "Summarize the Supreme Court decision in Loper Bright v. Raimondo regarding Chevron deference."
    inp = SanitizeTaskInput(payload_text=clean_text)
    res = sanitize_delegated_task_payload(inp)

    assert res.leak_prevented is False
    assert res.safety_verdict == "CLEAN"
    assert res.redactions_count == 0
    assert res.sanitized_payload == clean_text


def test_sanitize_delegated_task_payload_via_mcp(mcp_server):
    args = {
        "payload_text": "Authorization: Bearer mysecrettoken1234567890abcdefghijk",
    }
    res = mcp_server.call_tool("sanitize_delegated_task_payload", args)
    assert res["leak_prevented"] is True
    assert res["safety_verdict"] == "SANITIZED_SECRETS_STRIPPED"


# ============================================================================
# 4. Tests for auto_refund_dormant_escrow
# ============================================================================

def test_auto_refund_dormant_escrow_timeout_triggered():
    mgr = EscrowManager()
    contract = mgr.create_contract(
        client_id="client_payer",
        provider_id="provider_worker",
        service_fee=1000,
        provider_stake=200,
    )
    cid = contract.contract_id
    assert contract.status == "LOCKED"

    # Simulate dormancy: move created_at back 2 hours
    contract.created_at = datetime.now(UTC) - timedelta(hours=2)

    # Check timeout refund
    inp = DormantEscrowRefundInput(
        contract_id=cid,
        max_dormancy_seconds=3600,
    )
    res = auto_refund_dormant_escrow(inp, escrow_manager=mgr)

    assert res.refund_authorized is True
    assert res.current_status == "REFUNDED"
    assert res.refunded_credits == 1000
    assert contract.status == "REFUNDED"


def test_auto_refund_dormant_escrow_not_expired():
    mgr = EscrowManager()
    contract = mgr.create_contract(
        client_id="client_payer",
        provider_id="provider_worker",
        service_fee=1000,
        provider_stake=200,
    )
    cid = contract.contract_id

    # Newly created contract (0s elapsed)
    inp = DormantEscrowRefundInput(
        contract_id=cid,
        max_dormancy_seconds=3600,
    )
    res = auto_refund_dormant_escrow(inp, escrow_manager=mgr)

    assert res.refund_authorized is False
    assert res.current_status == "ACTIVE_NOT_EXPIRED"
    assert contract.status == "LOCKED"


def test_auto_refund_dormant_escrow_force_override():
    mgr = EscrowManager()
    contract = mgr.create_contract(
        client_id="client_payer",
        provider_id="provider_worker",
        service_fee=750,
        provider_stake=150,
    )
    cid = contract.contract_id

    # Force override immediate refund
    inp = DormantEscrowRefundInput(
        contract_id=cid,
        force_override=True,
    )
    res = auto_refund_dormant_escrow(inp, escrow_manager=mgr)

    assert res.refund_authorized is True
    assert res.current_status == "REFUNDED"
    assert res.refunded_credits == 750
    assert contract.status == "REFUNDED"


def test_auto_refund_dormant_escrow_via_mcp(mcp_server):
    contract = mcp_server.escrow.create_contract(
        client_id="client_payer_mcp",
        provider_id="provider_mcp",
        service_fee=500,
        provider_stake=100,
    )
    cid = contract.contract_id

    # Call tool with force_override
    res = mcp_server.call_tool(
        "auto_refund_dormant_escrow",
        {"contract_id": cid, "force_override": True},
    )
    assert res["refund_authorized"] is True
    assert res["current_status"] == "REFUNDED"
    assert res["refunded_credits"] == 500


def test_work_receipt_atomic_decision_digest_and_idempotency():
    inp = WorkReceiptInput(
        task_id="TASK-ATOMIC-999",
        client_agent_id="agent_alpha",
        provider_agent_id="agent_beta",
        input_payload="Compute corporate tax exposure under IRC Section 382",
        output_payload="No ownership change triggered under Section 382(g)",
        settlement_credits=350,
        execution_latency_ms=88.2,
        decision_timestamp_utc="2026-11-20T23:59:59Z",
        frozen_input_snapshot_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        idempotency_key="IDEMP-UNIQUE-KEY-001",
    )
    receipt = issue_verifiable_work_receipt(inp)
    assert receipt.idempotency_key == "IDEMP-UNIQUE-KEY-001"
    assert len(receipt.atomic_decision_digest) == 64
    assert receipt.deductible_accounting_record["idempotency_key"] == "IDEMP-UNIQUE-KEY-001"
    assert receipt.deductible_accounting_record["atomic_decision_digest"] == receipt.atomic_decision_digest


def test_sanitize_task_payload_with_capability_handles():
    raw_text = (
        "Authorize task with token sk-abcdef1234567890abcdef1234567890 "
        "and delegate via resource cap://res-4e89a1b02f8c/subtask and ref:vault:aws-read-secret."
    )
    inp = SanitizeTaskInput(payload_text=raw_text)
    res = sanitize_delegated_task_payload(inp)

    assert "sk-" not in res.sanitized_payload
    assert "cap://res-4e89a1b02f8c/subtask" in res.sanitized_payload
    assert "ref:vault:aws-read-secret" in res.sanitized_payload
    assert len(res.capability_handles_detected) == 2
    assert "cap://res-4e89a1b02f8c/subtask" in res.capability_handles_detected


def test_auto_refund_canary_probe_verified():
    mgr = EscrowManager()
    contract = mgr.create_contract(
        client_id="client_payer",
        provider_id="provider_worker",
        service_fee=1200,
        provider_stake=240,
    )
    inp = DormantEscrowRefundInput(
        contract_id=contract.contract_id,
        force_override=True,
        canary_probe_enabled=True,
    )
    res = auto_refund_dormant_escrow(inp, escrow_manager=mgr)
    assert res.canary_probe_verified is True
    assert res.canary_probe_latency_ms >= 0.0
    assert res.current_status == "REFUNDED"
