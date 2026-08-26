# BUILD_PLAN.md — ordered steps

Work through these in order. **Do not start a step before its predecessor's
verification passes.** Each step ends with a check you can run.

Read `CLAUDE.md` first — it holds the rules and the ground-truth numbers.

---

## Step 0 — Scaffold

Create the directory structure from `CLAUDE.md` §5, `requirements.txt`,
`.gitignore` (ignore `artifacts/*`, `.env`, `audit.db`, `__pycache__`), and a
placeholder `README.md`. Copy the provided `sample_docs/` into the repo.

**Verify:** `python -m src.main --help` prints the command list.

---

## Step 1 — Audit log (build this first, everything writes to it)

`src/audit/schema.sql` with an `audit_events` table:
`event_id, run_id, event_type, timestamp, actor, payload_json, prev_hash, hash`

Add triggers rejecting UPDATE and DELETE. Hash-chain each row to its
predecessor so tampering is detectable.

Event types to support: `graph_built`, `graph_approved`, `figure_computed`,
`config_loaded`, `narrative_generated`, `firewall_checked`, `reconciliation_run`,
`report_exported`.

**Verify:** `pytest tests/test_audit_append_only.py` — an UPDATE attempt raises,
a DELETE attempt raises, and the hash chain validates.

---

## Step 2 — Ingestion

`csv_loader.py`: parse all 13 rows into `Decimal` market values. Carry each
row's line number as provenance.

`pdf_parser.py`: use `pdfplumber` to extract the guideline tables. Target
section 2 (allocation limits), the non-IG note under it, section 3.1 (risk
metrics), 3.2 (concentration), 3.3 (liquidity), 4 (retention).

`chunker.py`: split the PDF into chunks with a **deterministic** `chunk_id`
(e.g. `chunk_` + first 4 hex of sha256 of the chunk text). Store page number
and character offsets.

Parse numeric limits with regex, **not** the LLM.

**Verify:** a script that prints every extracted limit with its page and
chunk_id. Check by eye against the PDF: SGS 20–60, MAS 0–40, IG Corp 10–50,
HY 0–15, FX 0–20, SC 0–10, Cash min 5, non-IG max 20, single issuer max 8,
GRE max 12, liquidity min 25, duration 2.0–6.5, DV01 max 85,000.

---

## Step 3 — Graph

`schema.py`: node and edge types.

Nodes: `Document`, `Chunk`, `AssetClass`, `Limit`, `RiskMetric`, `Threshold`,
`BreachAction`, `Owner`, `Issuer`, `Position`, `Aggregate`.

Edges: `HAS_LIMIT`, `HAS_THRESHOLD`, `ON_BREACH`, `NOTIFIES`, `ISSUED_BY`,
`PARENT_OF`, `BELONGS_TO`, `CONTRIBUTES_TO`, `SOURCED_FROM`.

Every node and edge carries: `source_doc`, `page`, `chunk_id`, `ingested_at`,
`extraction_confidence`.

`builder.py`: build the graph from ingestion output, then freeze it to
`artifacts/graph.json` with a content hash. Sort keys on write so the file is
byte-stable.

`traversal.py`: traversal helpers that **return the path they walked**, not
just the result. This is what produces `graph_path` later.

Add the human gate: nodes with `extraction_confidence < 0.9` or unresolved
references go into `artifacts/graph_review.json`; `approve-graph` records
approval in the audit log.

**Verify:** a multi-hop query answering *"if portfolio duration exceeds its
limit, what is the breach action and who is notified?"* by traversal only —
expected: PM notification within 1h. Log the path it walked.

---

## Step 4 — Config

`models.py`: pydantic models for the config schema in `CLAUDE.md` §8.
`loader.py`: load + validate YAML, record `config_loaded` in the audit log with
a hash of the config content.

Write both `config/firm_a.yaml` and `config/firm_b.yaml` **now**, before the
compute layer. Writing them first forces the compute layer to be config-driven
instead of retrofitted.

**Verify:** loading a deliberately broken YAML raises a clear validation error
naming the offending field.

---

## Step 5 — Compute (the core)

`aggregations.py`: generic primitives, no domain hardcoding —
`sum_by(positions, group_by_field)`, `filter_by(positions, predicate_spec)`,
`weighted_average(positions, value_field, weight_field)`.

`figures.py`: one function per figure, each of which
1. traverses the graph to collect the relevant nodes,
2. computes with `Decimal`,
3. resolves the limit by traversing to its `Limit` node,
4. returns value + `graph_path` + `citation`.

`formatters.py`: presentation only. Percent formatter and basis-point
formatter, both taking decimals and rounding mode from config.

Output shape per figure (exactly as the assignment specifies):
```json
{
  "figure": "aggregate_non_ig_exposure",
  "value": "15.0%",
  "status": "OK",
  "limit": "max 20%",
  "graph_path": "(AssetClass:high_yield)-[:CONTRIBUTES_TO]->(Aggregate:non_ig)<-[:CONTRIBUTES_TO]-(AssetClass:structured_credit)",
  "citation": {
    "source_doc": "sample_fund_guidelines.pdf",
    "page": 4,
    "chunk_id": "chunk_9c1a",
    "passage_summary": "Section 4.2 — aggregate non-investment-grade exposure cap"
  }
}
```

`graph_path` must be generated from the recorded traversal, never hand-written.

Compute duration and DV01 from the **unrounded** weighted average — see the
warning in `CLAUDE.md` §7.

**Verify:** all 13 Firm A figures match the ground-truth table exactly.

---

## Step 6 — Excel output

Read `report_template.xlsx` with openpyxl, fill Value / Limit / Utilization /
Status / Source columns, write to `artifacts/<run_id>/report_firm_A.xlsx`.
Never modify the template in place.

The Source column gets a compact `graph_path → doc p.N` string.

**Verify:** open the output; all 13 rows populated, template still blank.

---

## Step 7 — Firm B

Run `--firm B` with **no code changes at all**. If anything needs editing in
`src/compute/`, the config design is wrong — fix the config layer, not the
engine.

**Verify:**
- non-IG = 21.0% BREACH
- largest GRE = 13.0% BREACH
- every utilization renders as bps (`5833 bps`, `2000 bps`, `6600 bps`, ...)
- all other values unchanged from Firm A
- `git diff` across the two runs touches nothing under `src/`

---

## Step 8 — Narrative + firewall

`generator.py`: send **only** the computed figures JSON to Claude. Never the
CSV, never the PDF. Ask for prose commentary on breaches and their required
actions.

`firewall.py`: extract numeric tokens from the narrative, normalise, compare to
the computed set, whitelist non-figure numbers. Reject on any leftover.

**Verify:** with `ANTHROPIC_API_KEY` unset, `run` still emits all 13 figures
identically and leaves narrative empty. Then add a deliberately wrong number to
a test narrative string and confirm the firewall rejects it.

---

## Step 9 — Evaluate

`compare.py`: read `firm_A_answer_key.xlsx`, diff every figure, report
pass/fail + delta.

`report.py`: print the three checks — reconciliation table, traceability
(every figure resolves to a source), firewall result. Plus
`verify-determinism` running the pipeline twice and comparing hashes.

**Verify:** 13/13 pass for Firm A. Traceability 13/13. Firewall clean.
Determinism hashes equal.

---

## Step 10 — Tests

- `test_no_llm_in_compute.py` — grep `src/compute/` and `src/graph/` for
  forbidden imports
- `test_no_firm_names_in_engine.py` — grep for firm identifiers
- `test_determinism.py` — run twice, assert identical figure JSON
- `test_audit_append_only.py` — already written in Step 1
- `test_untraceable_figure_errors.py` — remove a citation, assert ERROR status
  rather than a bare value

---

## Step 11 — Docs

Write these **last in code order but reflecting decisions already made** — they
must describe what the repo actually does.

`docs/01_flow_and_audit_events.md`
- AS-IS: analyst reads PDF → spreadsheet → types into template
- TO-BE: the pipeline, marking autonomous vs human-reviewed steps
- Gates with explicit criteria, e.g. *graph approval: auto-pass when every node
  has `extraction_confidence ≥ 0.9` and passes schema validation; otherwise
  human review*
- Audit event catalogue table: Event | Trigger | Data Captured | Retention

`docs/02_architecture.md`
- Layer diagram (mermaid is fine): Ingestion → Graph → Compute → Reconcile →
  Narrative → Export, with Audit Log crossing all layers
- Mark clearly where the LLM may and may not appear

`docs/03_rfc.md` — prose, no code. Must answer four questions:
1. How the LLM is *structurally* unable to source any number (dependency
   isolation, input restriction, firewall verification, and the
   API-key-removed acceptance test)
2. How a figure traces through the graph to its source
3. How a firm's method is expressed and switched (config as validated data,
   not code; adding a firm = adding a YAML file)
4. How output reconciles to an answer key, and what tolerance is claimed and why
   (exact for percentages and status; rounding rules stated explicitly)

Also state honestly: ingestion may use an LLM for non-numeric extraction and is
therefore not deterministic — which is why its output is frozen and
human-approved before the deterministic reporting pipeline consumes it.

---

## Step 12 — README

- One-command start
- The full command list with what each does
- How to switch firms
- How to run the evaluation
- What you would add for production (secrets management, auth, real graph DB,
  richer failure handling) — the assignment asks for this note

---

## Step 13 — Bonus, only if 5–9 are complete

Add `python -m src.main viewer` that reads `artifacts/<run>/figures.json` and
writes a single self-contained `viewer.html` — one file, inline CSS and JS, no
server, no build step. For each figure show: value, graph path, source citation,
delta vs answer key, and which config rule produced it.

Do not add a web framework. Do not let the viewer trigger computation — it only
reads artifacts.
