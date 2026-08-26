# Flow and Audit Events

## AS-IS

An analyst opens `sample_fund_guidelines.pdf`, reads the allocation limits
and risk thresholds off its tables by eye, opens `sample_holdings.csv` (or
an equivalent extract from the portfolio system) in a spreadsheet, computes
each allocation percentage and risk metric by hand or with spreadsheet
formulas, compares each one against the limit they remembered or looked up
again, and types the results into `report_template.xlsx`.

Nothing here is wrong in isolation, but nothing is checked either. There is
no record of which cell in the spreadsheet fed which number in the report,
no record of which page of the PDF a limit came from, no way to tell months
later whether a number was mistyped, and no way to reproduce the exact
figures if a formula cell was later edited. If the analyst made an arithmetic
slip on the DV01 calculation, the only way to catch it is another analyst
independently redoing the same manual work.

## TO-BE

The pipeline replaces the manual middle of that process with a fixed
sequence of deterministic steps, with one explicit point where a human is
asked to look at something before it's trusted. Steps are marked
**[Autonomous]** (runs without a person) or **[Human-reviewed]** (a person
must act before downstream steps can trust the output).

1. **Ingest** `[Autonomous]` — `ingest` command. Parses
   `sample_fund_guidelines.pdf` (regex/table extraction, never an LLM, for
   every numeric limit) and `sample_holdings.csv` into typed records, builds
   the compliance graph, and freezes it to `artifacts/graph.json` with a
   content hash.
2. **Graph approval gate** `[Human-reviewed, conditionally]` — every node
   ingestion produced carries an `extraction_confidence`. If every node is
   `>= 0.9` and the graph parses correctly, `ingest` auto-passes and records
   `graph_approved` itself (`actor: system`, `method: auto-pass`). If any
   node falls below that, ingestion writes the offending nodes to
   `artifacts/graph_review.json` and refuses to auto-approve — a human must
   read that file and run `approve-graph --run-id <id>` before `run` will
   trust the graph. `--auto-approve` on `ingest` skips this gate outright
   for demo runs, and that shortcut is itself recorded in the audit log
   (`method: auto-approve`) so it's never silent.
3. **Compute** `[Autonomous]` — `run --firm A|B`. Loads the frozen graph
   (never re-parses the PDF/CSV) and the chosen firm's config, computes all
   13 figures via graph traversal with `Decimal` arithmetic, and renders
   them to display strings only at the very end.
4. **Export** `[Autonomous]` — fills `report_template.xlsx` (never
   modified in place) and writes `figures.json` (every figure plus its
   graph path and source citation).
5. **Narrative** `[Autonomous, optional]` — sends only the already-computed
   figures JSON to Claude for prose commentary. Skipped entirely (empty
   narrative, no network call) if `ANTHROPIC_API_KEY` is unset.
6. **Firewall** `[Autonomous]` — deterministic token check: every number in
   the narrative must appear in the computed figures (or match a narrow
   whitelist for years / section references / durations-with-units). A
   narrative that fails is discarded, not published — `run` still succeeds.
7. **Evaluate** `[Autonomous]` — `evaluate --firm A|B`. Diffs every figure
   against the answer key, confirms every figure resolves to a real
   `graph_path` and citation, and re-checks the firewall.

The only step that ever blocks on a person is step 2, and only when the data
actually warrants it — clean extractions (which is what this particular
guidelines document produces) sail through without anyone touching it.

## Audit event catalogue

Every event below is appended to `audit_events` (SQLite, append-only —
UPDATE/DELETE are rejected by trigger, see `src/audit/schema.sql`) and
chained by hash to the row before it, so tampering with a past row is
detectable (`verify_chain`). Payloads shown are exactly what
`src/main.py` records — see the file for the literal call sites.

| Event | Trigger | Data captured | Retention |
|---|---|---|---|
| `graph_built` | `ingest` finishes building and freezing the graph | `content_hash`, `node_count`, `edge_count` | Indefinite — `audit_events` has no delete path by design (section 3.6) |
| `graph_approved` | Auto-pass (all nodes ≥ 0.9 confidence), `--auto-approve`, or a human running `approve-graph` | `method` (`auto-pass` / `auto-approve` / `manual`), `reviewed_items` or `review_items_skipped` count | Indefinite |
| `config_loaded` | `run` or `evaluate` loads a firm's YAML config | config file name, its own content hash, the config's `label` | Indefinite |
| `figure_computed` | Once per figure, during `run` (13 events per run) | figure name, resulting status | Indefinite |
| `narrative_generated` | The LLM successfully returns narrative text | narrative length in characters (not the text itself — the text lives only in `figures.json`) | Indefinite |
| `firewall_checked` | Immediately after a narrative is generated | `passed` (bool), `rejected_tokens` (list, empty if clean) | Indefinite |
| `report_exported` | `run` finishes writing the Excel report and `figures.json` | both output file paths | Indefinite |
| `reconciliation_run` | `evaluate` finishes its three checks | firm, figures reconciled / total, traceability pass/fail, firewall pass/fail | Indefinite |

The guidelines PDF itself specifies retention periods for various *reports*
(7 years for transaction data, 10 years for investor-facing reports,
permanent for the annual compliance report — section 4/5.1). Those govern
how long the *business records* (the Excel report, `figures.json`) should be
kept in a production deployment; this repo doesn't implement a deletion or
archival job for either the audit log or the exported artifacts — `Indefinite`
above describes what the code actually does today, not a retention policy
that's been engineered in. Enforcing those retention windows in a real
system is called out explicitly in the README's "what I'd add for
production" section.
