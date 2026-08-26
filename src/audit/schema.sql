-- Append-only audit log. See CLAUDE.md section 3.6 and BUILD_PLAN.md Step 1.
--
-- Rows are never updated or deleted (triggers below enforce this at the
-- database level, not just in application code). Each row's `hash` is a
-- sha256 digest that folds in `prev_hash`, so the rows form a hash chain:
-- altering or removing any past row breaks the chain from that point on.

CREATE TABLE IF NOT EXISTS audit_events (
    event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL,
    event_type    TEXT NOT NULL CHECK (event_type IN (
                      'graph_built',
                      'graph_approved',
                      'figure_computed',
                      'config_loaded',
                      'narrative_generated',
                      'firewall_checked',
                      'reconciliation_run',
                      'report_exported'
                  )),
    timestamp     TEXT NOT NULL,
    actor         TEXT NOT NULL,
    payload_json  TEXT NOT NULL,
    prev_hash     TEXT NOT NULL,
    hash          TEXT NOT NULL UNIQUE
);

CREATE TRIGGER IF NOT EXISTS audit_events_forbid_update
BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only: UPDATE is forbidden');
END;

CREATE TRIGGER IF NOT EXISTS audit_events_forbid_delete
BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only: DELETE is forbidden');
END;
