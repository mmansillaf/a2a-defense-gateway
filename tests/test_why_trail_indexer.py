"""Tests para el indexador Why-Trail en SQLite (why_trail_indexer.py)."""

import json
from pathlib import Path

import pytest
from why_trail_indexer import get_why_trail_metrics_summary, init_why_trail_db, sync_ledger_to_sqlite


def test_init_and_sync_why_trail_sqlite(tmp_path: Path):
    test_db = tmp_path / "test_why_trail.sqlite3"
    test_ledger = tmp_path / "test_ledger.jsonl"

    entries = [
        {
            "sequence_index": 0,
            "timestamp": "2026-11-23T10:00:00Z",
            "event_type": "HTTP_GET:/",
            "actor_agent_id": "agent_alpha",
            "block_hash": "hash0",
            "metadata": {},
        },
        {
            "sequence_index": 1,
            "timestamp": "2026-11-23T10:01:00Z",
            "event_type": "TOOL_CALL:audit_eip7702_delegation",
            "actor_agent_id": "agent_beta",
            "block_hash": "hash1",
            "metadata": {"status": "SUCCESS"},
        },
        {
            "sequence_index": 2,
            "timestamp": "2026-11-23T10:02:00Z",
            "event_type": "HOOK_BLOCKED",
            "actor_agent_id": "agent_malicious",
            "block_hash": "hash2",
            "metadata": {"threat_level": "CRITICAL"},
        },
    ]

    with test_ledger.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")

    # Primera indexación
    new_count = sync_ledger_to_sqlite(ledger_path=test_ledger, db_path=test_db)
    assert new_count == 3

    # Idempotencia: segunda indexación no debe duplicar
    re_sync = sync_ledger_to_sqlite(ledger_path=test_ledger, db_path=test_db)
    assert re_sync == 0

    # Verificar métricas
    metrics = get_why_trail_metrics_summary(db_path=test_db)
    assert metrics["total_events"] == 3
    assert metrics["total_tool_calls"] == 1
    assert metrics["blocked_threats"] == 1
    assert metrics["unique_callers"] == 3
    assert metrics["threat_distribution"].get("CRITICAL") == 1
