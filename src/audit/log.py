"""Append-only, hash-chained audit event log (CLAUDE.md section 3.6).

Every event is written with a sha256 hash that folds in the previous event's
hash, forming a chain across the whole table (not scoped per run_id) — so
`verify_chain` can detect any row that was altered after the fact, on top of
the UPDATE/DELETE triggers defined in schema.sql.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

GENESIS_HASH = "0" * 64

EVENT_TYPES = frozenset(
    {
        "graph_built",
        "graph_approved",
        "figure_computed",
        "config_loaded",
        "narrative_generated",
        "firewall_checked",
        "reconciliation_run",
        "report_exported",
    }
)


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open (creating if needed) the audit database and ensure its schema exists."""
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _last_hash(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT hash FROM audit_events ORDER BY event_id DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else GENESIS_HASH


def _row_hash(
    run_id: str,
    event_type: str,
    timestamp: str,
    actor: str,
    payload_json: str,
    prev_hash: str,
) -> str:
    digest_input = "|".join([run_id, event_type, timestamp, actor, payload_json, prev_hash])
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


def append_event(
    conn: sqlite3.Connection,
    run_id: str,
    event_type: str,
    actor: str,
    payload: dict[str, Any],
) -> str:
    """Append one event to the log and return its hash."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event_type: {event_type!r}")

    prev_hash = _last_hash(conn)
    timestamp = datetime.now(timezone.utc).isoformat()
    payload_json = _canonical_json(payload)
    row_hash = _row_hash(run_id, event_type, timestamp, actor, payload_json, prev_hash)

    conn.execute(
        """
        INSERT INTO audit_events
            (run_id, event_type, timestamp, actor, payload_json, prev_hash, hash)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, event_type, timestamp, actor, payload_json, prev_hash, row_hash),
    )
    conn.commit()
    return row_hash


def verify_chain(conn: sqlite3.Connection) -> bool:
    """Recompute every row's hash and confirm the prev_hash chain is unbroken."""
    rows = conn.execute(
        "SELECT run_id, event_type, timestamp, actor, payload_json, prev_hash, hash "
        "FROM audit_events ORDER BY event_id ASC"
    ).fetchall()

    expected_prev = GENESIS_HASH
    for run_id, event_type, timestamp, actor, payload_json, prev_hash, hash_ in rows:
        if prev_hash != expected_prev:
            return False
        if _row_hash(run_id, event_type, timestamp, actor, payload_json, prev_hash) != hash_:
            return False
        expected_prev = hash_
    return True
