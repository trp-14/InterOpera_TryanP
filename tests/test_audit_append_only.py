import sqlite3

import pytest

from src.audit import log as audit_log


@pytest.fixture
def conn(tmp_path):
    connection = audit_log.connect(tmp_path / "audit.db")
    yield connection
    connection.close()


def test_update_raises(conn):
    audit_log.append_event(conn, run_id="run-1", event_type="graph_built", actor="system", payload={"n": 1})
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE audit_events SET actor = 'tampered' WHERE event_id = 1")


def test_delete_raises(conn):
    audit_log.append_event(conn, run_id="run-1", event_type="graph_built", actor="system", payload={"n": 1})
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM audit_events WHERE event_id = 1")


def test_unknown_event_type_rejected(conn):
    with pytest.raises(ValueError):
        audit_log.append_event(conn, run_id="run-1", event_type="not_a_real_event", actor="system", payload={})


def test_hash_chain_validates(conn):
    audit_log.append_event(conn, run_id="run-1", event_type="graph_built", actor="system", payload={"a": 1})
    audit_log.append_event(conn, run_id="run-1", event_type="graph_approved", actor="human", payload={"b": 2})
    audit_log.append_event(conn, run_id="run-1", event_type="figure_computed", actor="system", payload={"c": 3})

    assert audit_log.verify_chain(conn) is True


def test_hash_chain_links_sequential_events(conn):
    hash_1 = audit_log.append_event(conn, run_id="run-1", event_type="graph_built", actor="system", payload={})
    hash_2 = audit_log.append_event(conn, run_id="run-1", event_type="graph_approved", actor="human", payload={})

    prev_hash_of_second_row = conn.execute(
        "SELECT prev_hash FROM audit_events WHERE event_id = 2"
    ).fetchone()[0]

    assert hash_1 != hash_2
    assert prev_hash_of_second_row == hash_1


def test_hash_chain_detects_tampering(conn):
    audit_log.append_event(conn, run_id="run-1", event_type="graph_built", actor="system", payload={"a": 1})
    audit_log.append_event(conn, run_id="run-1", event_type="graph_approved", actor="human", payload={"b": 2})

    # UPDATE/DELETE are blocked by triggers, but a corrupted row could still
    # reach the table some other way (e.g. a hand-edited copy of the file
    # opened outside this app). Simulate that by inserting a row whose hash
    # was computed from different content than what's stored, and confirm
    # verify_chain catches the mismatch rather than trusting the stored hash.
    conn.execute(
        """
        INSERT INTO audit_events
            (run_id, event_type, timestamp, actor, payload_json, prev_hash, hash)
        VALUES ('run-1', 'figure_computed', '2026-01-01T00:00:00+00:00', 'system', '{}', 'not-the-real-prev-hash', 'deadbeef')
        """
    )
    conn.commit()

    assert audit_log.verify_chain(conn) is False
