# Meridian Fixed Income Fund — Compliance Report Pipeline

A CLI pipeline that turns a fund's investment guidelines (PDF) and its
holdings (CSV) into an auditable compliance report — every figure carries a
graph path back to the exact table row it was extracted from, and the same
engine serves two firms with different calculation methods, switched purely
by config file.

See [CLAUDE.md](CLAUDE.md) for the full rule set and ground-truth numbers
this repo is built against, [BUILD_PLAN.md](BUILD_PLAN.md) for the build
order, and [docs/](docs/) for the architecture and design rationale.

## Requirements

- Python 3.10 or later (CLAUDE.md specifies 3.11+; this repo was built and
  tested against 3.10 — everything in `requirements.txt` is compatible with
  either)
- No external services required to produce a report. `ANTHROPIC_API_KEY` is
  optional — it only enables narrative commentary (see below); every figure
  computes identically with or without it.

## Quickstart

```bash
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt

python -m src.main ingest --auto-approve
python -m src.main run --firm A
```

That last command writes `artifacts/<run-id>/report_firm_A.xlsx` and
`artifacts/<run-id>/figures.json`. `--auto-approve` skips the human review
gate for this quickstart — see below for what that gate actually does.

## Commands

| Command | What it does |
|---|---|
| `ingest [--auto-approve]` | Parses `sample_docs/sample_fund_guidelines.pdf` and `sample_docs/sample_holdings.csv`, builds the compliance graph, and freezes it to `artifacts/graph.json`. If every node's extraction confidence is ≥ 0.9, it auto-approves itself; otherwise it writes `artifacts/graph_review.json` and waits for `approve-graph`. `--auto-approve` skips that check outright (recorded in the audit log as such) — use it for demos, not for a real approval workflow. |
| `approve-graph --run-id <id>` | Records a human's approval of a graph `ingest` printed a run ID for. Rejects an unrecognised run ID rather than approving blindly. |
| `run --firm A\|B` | Reads the frozen graph (never re-parses the PDF/CSV), loads the chosen firm's config, computes all 13 figures, writes the Excel report and `figures.json`, and — if `ANTHROPIC_API_KEY` is set — generates narrative commentary and firewall-checks it before including it. |
| `evaluate --firm A\|B` | Recomputes the figures and runs three checks: reconciliation against the answer key, traceability (every figure resolves to a real graph path and source citation), and a firewall check on any narrative. Exits non-zero if any check fails. |
| `trace <figure_name> [--firm A\|B]` | Prints one figure's value, status, graph path, and source citation — useful for spot-checking how a specific number was derived. Defaults to Firm A's config. |
| `verify-determinism --firm A\|B` | Computes the same firm's figures twice in the same process and confirms the output hashes match. |

Run any command with no arguments to see its exact flags
(`python -m src.main --help`, or `python -m src.main <command> --help`).

## Switching firms

`--firm A` and `--firm B` select `config/firm_a.yaml` or `config/firm_b.yaml`
— that's the entire difference. The compute engine (`src/compute/`,
`src/graph/`, `src/ingestion/`) contains no firm-specific code at all; this
isn't just a design goal, it's checked by
[tests/test_no_firm_names_in_engine.py](tests/test_no_firm_names_in_engine.py),
and was confirmed directly by running `git diff` on `src/` before and after
switching firms mid-session — nothing changed.

Three things differ between the two configs: how utilization is presented
(percentage vs. truncated basis points), which positions count toward the
aggregate non-investment-grade exposure figure, and how government-related
entities are grouped for the concentration cap. See
[docs/03_rfc.md](docs/03_rfc.md) section 3 for the full explanation, and
[sample_docs/firm_B_brief.md](sample_docs/firm_B_brief.md) for the source
brief.

To add a third firm's method: write `config/firm_c.yaml` using the same
schema (validated by `src/config/models.py`), and add `"C"` to the `--firm`
choices in `src/main.py`'s argument parser — the one place a firm letter is
still spelled out in code, and it's outside the engine boundary the "no firm
knowledge" rule actually draws.

## Running the evaluation

```bash
python -m src.main evaluate --firm A
python -m src.main evaluate --firm B
python -m src.main verify-determinism --firm A
```

`evaluate` prints three sections — Reconciliation (every figure's value/status/limit
against the answer key), Traceability (does every figure resolve to a graph
path and citation), and Firewall (is any generated narrative clean) — then a
pass/fail summary. Firm A reconciles against the provided
`sample_docs/firm_A_answer_key.xlsx` directly; no answer-key workbook was
provided for Firm B, so `evaluate --firm B` derives its reference from that
same workbook with the two documented differences overridden (see
`src/reconcile/compare.py`).

The full automated test suite (`pytest`) covers all of this plus the
append-only audit log, config validation, and the untraceable-figure error
path — run `pytest` from the repo root after installing dependencies.

## What I'd add for production

This is a homework-scoped implementation of a real design; a production
deployment would need at least:

- **Secrets management.** `ANTHROPIC_API_KEY` is read directly from the
  environment. A real deployment would pull it from a vault/secrets manager
  at process start, rotate it, and never let it land in a process
  environment variable that a crash dump or debugger could expose.
- **Authentication and authorization.** There is no user identity anywhere
  in this system — the audit log's `actor` field is a fixed string
  (`"system"`, `"human"`, `"llm"`), not a real logged-in person. A
  production version needs real auth, and `approve-graph` in particular
  needs to record *who* approved, not just *that* someone did.
- **A real graph database.** The graph is an in-memory `networkx`
  `MultiDiGraph`, rebuilt or reloaded from a single JSON file on every
  process run — fine at ~60 nodes, but it doesn't support concurrent
  writers, doesn't scale past what fits in memory, and has no query
  language beyond the traversal helpers this repo hand-wrote. Neo4j (or
  similar) would be the natural next step once more than one person or
  process needs to touch the graph at once.
- **Richer failure handling.** `compute_all_figures` catches any exception
  per-figure and turns it into a generic `ERROR` record — correct in spirit
  (no crash, no silent bad number) but not diagnostically rich. Production
  would want distinct error types (missing node vs. bad data vs. config
  mismatch), retries for transient failures (an LLM API timeout shouldn't
  be treated the same as a permanently broken citation), and structured
  logging/alerting in place of the `print()` statements this CLI uses.
- **Retention enforcement.** The guidelines document specifies retention
  periods for various reports (7/10 years, permanent for the annual
  compliance report). This repo's audit log and exported artifacts are
  append-only and undeleted by design, but nothing here actually enforces
  *when* records may finally be archived or purged — see
  [docs/01_flow_and_audit_events.md](docs/01_flow_and_audit_events.md).
