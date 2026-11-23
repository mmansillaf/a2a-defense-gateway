"""Why-Trail SQLite Indexer & Real-Time Metrics Engine.

Indexa el registro append-only data/multi_camel_ledger.jsonl hacia una base de
datos SQLite embebida de alta velocidad (data/why_trail.sqlite3) y expone
métricas analíticas y de auditoría para el Dashboard y endpoints REST.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_LEDGER_PATH = BASE_DIR / "data" / "a2a_audit_ledger.jsonl"
FALLBACK_LEDGER_PATH = BASE_DIR / "data" / "multi_camel_ledger.jsonl"
DEFAULT_DB_PATH = BASE_DIR / "data" / "why_trail.sqlite3"


def init_why_trail_db(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Inicializa el esquema de base de datos SQLite para Why-Trail."""
    path_obj = Path(db_path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path_obj))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS why_trail_events (
                sequence_index INTEGER PRIMARY KEY,
                timestamp TEXT,
                event_type TEXT,
                actor_agent_id TEXT,
                target_agent_id TEXT,
                tool_name TEXT,
                threat_level TEXT,
                is_threat_blocked INTEGER DEFAULT 0,
                execution_latency_ms REAL DEFAULT 0.0,
                block_hash TEXT,
                raw_json TEXT
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_why_trail_tool ON why_trail_events(tool_name);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_why_trail_actor ON why_trail_events(actor_agent_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_why_trail_threat ON why_trail_events(threat_level);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_why_trail_event_type ON why_trail_events(event_type);")

    return conn


def sync_ledger_to_sqlite(
    ledger_path: str | Path = DEFAULT_LEDGER_PATH,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """Indexa de forma idempotente eventos nuevos desde el JSONL al SQLite."""
    ledger_file = Path(ledger_path)
    if not ledger_file.exists():
        return 0

    conn = init_why_trail_db(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COALESCE(MAX(sequence_index), -1) FROM why_trail_events;")
    max_indexed = cursor.fetchone()[0]

    new_records = 0
    with ledger_file.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            clean = line.strip()
            if not clean:
                continue
            try:
                entry = json.loads(clean)
            except json.JSONDecodeError:
                continue

            seq = entry.get("sequence_index", -1)
            if seq <= max_indexed:
                continue

            ts = entry.get("timestamp", "")
            ev_type = entry.get("event_type", "UNKNOWN")
            actor = entry.get("actor_agent_id", "")
            target = entry.get("target_agent_id", "")
            payload = entry.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}

            tool_name = payload.get("tool_name") or payload.get("name") or ""
            if not tool_name and ev_type.startswith("TOOL_CALL:"):
                tool_name = ev_type.split(":", 1)[1].strip()

            meta = entry.get("metadata", {})
            if not isinstance(meta, dict):
                meta = {}

            threat_level = payload.get("threat_level") or payload.get("threat") or meta.get("threat_level") or "CLEAN"
            is_blocked = 1 if (
                payload.get("status") == "BLOCKED"
                or meta.get("status") == "BLOCKED"
                or "HOOK_VIOLATION" in str(payload.get("error", ""))
                or ev_type in ("HOOK_BLOCKED", "SECURITY_VIOLATION", "RATE_LIMIT_EXCEEDED")
                or threat_level in ("CRITICAL", "HIGH", "SUSPICIOUS")
            ) else 0

            latency = float(payload.get("execution_latency_ms", payload.get("latency_ms", 0.0)))
            b_hash = entry.get("block_hash", "")

            cursor.execute(
                """
                INSERT OR IGNORE INTO why_trail_events (
                    sequence_index, timestamp, event_type, actor_agent_id,
                    target_agent_id, tool_name, threat_level, is_threat_blocked,
                    execution_latency_ms, block_hash, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    seq,
                    ts,
                    ev_type,
                    actor,
                    target,
                    tool_name,
                    threat_level,
                    is_blocked,
                    latency,
                    b_hash,
                    clean,
                ),
            )
            new_records += 1

    conn.commit()
    conn.close()
    return new_records


def get_why_trail_metrics_summary(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Genera métricas consolidadas en tiempo real a partir del índice SQLite."""
    conn = init_why_trail_db(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM why_trail_events;")
    total_events = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM why_trail_events WHERE tool_name != '' OR event_type LIKE '%TOOL%';"
    )
    total_tool_calls = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM why_trail_events WHERE is_threat_blocked = 1;")
    blocked_threats = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(AVG(execution_latency_ms), 0.0) FROM why_trail_events WHERE execution_latency_ms > 0;")
    avg_latency = round(cursor.fetchone()[0], 2)

    cursor.execute("SELECT COUNT(DISTINCT actor_agent_id) FROM why_trail_events WHERE actor_agent_id != '';")
    unique_callers = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT tool_name, COUNT(*) as cnt
        FROM why_trail_events
        WHERE tool_name != ''
        GROUP BY tool_name
        ORDER BY cnt DESC
        LIMIT 5;
        """
    )
    top_tools = [{"tool": row[0], "count": row[1]} for row in cursor.fetchall()]

    cursor.execute(
        """
        SELECT COALESCE(threat_level, 'CLEAN') as tl, COUNT(*)
        FROM why_trail_events
        GROUP BY tl;
        """
    )
    threat_dist = {row[0]: row[1] for row in cursor.fetchall()}

    cursor.execute("SELECT COALESCE(MAX(timestamp), 'Sin datos') FROM why_trail_events;")
    last_event_ts = cursor.fetchone()[0]

    conn.close()

    return {
        "status": "HEALTHY",
        "total_events": total_events,
        "total_tool_calls": total_tool_calls,
        "blocked_threats": blocked_threats,
        "avg_latency_ms": avg_latency,
        "unique_callers": unique_callers,
        "top_tools": top_tools,
        "threat_distribution": threat_dist,
        "last_event_timestamp": last_event_ts,
    }


if __name__ == "__main__":
    n = sync_ledger_to_sqlite()
    metrics = get_why_trail_metrics_summary()
    print(f"Indexados {n} eventos nuevos. Resumen:", json.dumps(metrics, indent=2))
