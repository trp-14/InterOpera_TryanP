# CLAUDE.md — Project rules

Read this before every task. These rules are not suggestions; they are the
grading criteria of the assignment this repo answers.

---

## 1. What this project is

A **CLI pipeline** (not a web app) that produces an auditable portfolio
compliance report for a fictional Singapore fund (Meridian Fixed Income Fund).

It reads:
- `sample_docs/sample_fund_guidelines.pdf` — the rules (limits, thresholds, caps)
- `sample_docs/sample_holdings.csv` — the positions (13 instruments)

It produces:
- a filled `report_template.xlsx`
- a JSON figure set where **every number carries a graph path and a source citation**
- an append-only audit log

The system must serve **two firms** (A and B) that compute several figures
differently, **switchable by configuration only**.

---

## 2. The five hard constraints — inviolable

| # | Constraint | How this repo satisfies it |
|---|---|---|
| 1 | **Reproducible** — two runs on the same inputs produce identical figures | `Decimal` everywhere, explicit rounding, deterministic iteration order, sorted JSON keys, no timestamps inside figure payloads, LLM never called during report generation |
| 2 | **Traceable** — every figure follows `figure → graph path → source chunk` | Every figure is computed by traversing the graph; the traversal records the nodes/edges it visited and the source chunk at the end of the path |
| 3 | **No LLM-produced numbers** | `src/compute/` and `src/graph/` have zero LLM imports (enforced by test); the narrative layer receives only already-computed figures; a firewall rejects any numeric token in narrative text absent from the computed set |
| 4 | **Reconciles to Firm A's answer key** | `evaluate` command diffs every figure against `firm_A_answer_key.xlsx` |
| 5 | **Reconfigurable to Firm B without engine-code edits** | Firm methods live in `config/*.yaml`; the engine contains no firm identifier |

**If a change would violate any of these, stop and say so instead of making it.**

---

## 3. Rules the engine must obey

### 3.1 No firm knowledge in the engine
There must be **no string `"A"` / `"B"` / `"firm_a"` / `"firm_b"` anywhere
under `src/compute/`, `src/graph/`, or `src/ingestion/`**. Firm differences are
expressed as config values only.

Mental test before writing any `if`: *is this actually a config knob?*
If a hypothetical Firm C wanted different behaviour here, would they need to
edit Python? If yes, the design is wrong.

### 3.2 No LLM in the number path
- `src/compute/**` and `src/graph/**` must never import `anthropic`, `openai`,
  `httpx`, or anything under `src/narrative/`.
- There is a test that greps for this. Do not weaken it.
- **Acceptance test:** with `ANTHROPIC_API_KEY` unset, `run` must still produce
  a complete, identical set of figures. Only the narrative field is empty.

### 3.3 Decimal only, never float
- All money, percentages, durations, and ratios use `decimal.Decimal`.
- Never `float()`, never `round()`, never pandas for figure computation.
- Rounding is always explicit: `.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)`.
- Rounding mode is a **config value**, not a hardcoded choice.

### 3.4 Figures come from the graph, not from the CSV
The compute layer must not read `sample_holdings.csv` directly. It reads
`Position` nodes from the graph. If a figure is computed without touching the
graph, that is a constraint-2 failure — the assignment explicitly calls this out.

### 3.5 Untraceable figures are errors, not silent numbers
If a figure cannot resolve `figure → graph_path → source chunk`, emit:
```json
{"figure": "...", "status": "ERROR", "error": "no traceable path to source"}
```
Never emit a bare value without a path and citation.

### 3.6 The audit log is append-only
SQLite with triggers that `RAISE(ABORT)` on UPDATE and DELETE. No code path
performs UPDATE or DELETE on `audit_events`. There is a test proving an UPDATE
attempt raises.

---

## 4. Tech stack — locked, do not substitute

| Purpose | Library | Notes |
|---|---|---|
| Language | Python 3.11+ | |
| Graph | `networkx` (`MultiDiGraph`) | in-memory; ~60 nodes, no server needed |
| PDF | `pdfplumber` | table extraction from the guidelines |
| CSV | `csv` stdlib | **not** pandas |
| Arithmetic | `decimal` stdlib | |
| Config | `pyyaml` + `pydantic` v2 | pydantic validates config schema |
| Excel | `openpyxl` | read template + answer key, write output |
| Audit log | `sqlite3` stdlib | append-only via triggers |
| LLM | `anthropic` SDK | **only** in `src/narrative/` |
| CLI | `argparse` stdlib | |
| Tests | `pytest` | |

Do **not** add: LangChain, LlamaIndex, pandas (except when reading the answer
key during reconciliation), any vector DB, any web framework, Neo4j, Docker.

---

## 5. Repo layout

```
src/
  ingestion/   pdf_parser.py  csv_loader.py  chunker.py
  graph/       builder.py  schema.py  traversal.py
  compute/     figures.py  aggregations.py  formatters.py   # ZERO llm imports
  config/      loader.py  models.py
  narrative/   generator.py  firewall.py                    # ONLY llm folder
  reconcile/   compare.py  report.py
  audit/       log.py  schema.sql
  main.py
config/        firm_a.yaml  firm_b.yaml
docs/          01_flow_and_audit_events.md  02_architecture.md  03_rfc.md
sample_docs/   (provided, read-only inputs — never modify)
artifacts/     (generated output, gitignored except .gitkeep)
tests/
```

---

## 6. CLI surface

```bash
pip install -r requirements.txt

python -m src.main ingest                       # build graph, freeze to artifacts/graph.json
python -m src.main approve-graph --run-id <id>  # human gate
python -m src.main run --firm A                 # produce report
python -m src.main run --firm B
python -m src.main evaluate --firm A            # reconcile + traceability + firewall
python -m src.main trace <figure_name>          # print one figure's path to source
python -m src.main verify-determinism --firm A  # run twice, compare hashes
```

`--auto-approve` on `ingest` skips the human gate for demo runs (and is
recorded in the audit log as such).

---

## 7. Ground truth — verified, use these to test

**NAV = SGD 100,000,000** (sum of all 13 positions).

### Firm A expected output (must match exactly)

| Section | Metric | Value | Limit | Utilization | Status |
|---|---|---|---|---|---|
| Allocation | Singapore Government Securities | 35.0% | 20–60% | 58.3% | OK |
| Allocation | MAS Bills | 8.0% | 0–40% | 20.0% | OK |
| Allocation | Investment Grade Corporate Bonds | 33.0% | 10–50% | 66.0% | OK |
| Allocation | High Yield Bonds | 9.0% | 0–15% | 60.0% | OK |
| Allocation | Foreign Currency Bonds (hedged) | 5.0% | 0–20% | 25.0% | OK |
| Allocation | Structured Credit (ABS/MBS) | 6.0% | 0–10% | 60.0% | OK |
| Allocation | Cash & Cash Equivalents | 4.0% | min 5% | n/a | **BREACH** |
| Aggregate | Aggregate non-IG exposure | 15.0% | max 20% | 75.0% | OK |
| Concentration | Largest single corporate issuer | 8.0% | max 8% | 100.0% | **AT LIMIT** |
| Concentration | Largest GRE issuer | 7.0% | max 12% | 58.3% | OK |
| Liquidity | Liquid assets ratio | 47.0% | min 25% | 188.0% | OK |
| Market risk | Portfolio modified duration | 3.88 yrs | 2.0–6.5 yrs | n/a | OK |
| Market risk | Portfolio DV01 | SGD 38,790 / bp | max 85,000 | 45.6% | OK |

### Derivations

- Allocation % = asset-class market value ÷ NAV
- Utilization vs a **max** limit = value ÷ max. Vs a **min-only** limit (cash) = `n/a`
- Liquid assets = SGS + MAS Bills + Cash = 35 + 8 + 4 = 47%; utilization = 47 ÷ 25 = 188.0%
- Aggregate non-IG (Firm A) = High Yield + Structured Credit = 9 + 6 = 15%
  (this follows the literal guidelines note, even though the ABS is AAA-rated)
- Largest single corporate issuer = Changi Logistics 8% (Singapore Government excluded)
- Largest GRE issuer (Firm A) = Redhill Power 7%, measured per issuer
- Portfolio modified duration = market-value-weighted average = **3.879** → displayed `3.88`
- Portfolio DV01 = NAV × **3.879** × 0.0001 = 38,790

> **Critical:** DV01 uses the *unrounded* 3.879, not the displayed 3.88.
> Using 3.88 gives 38,800 and fails reconciliation. Round only at presentation.

- DV01 utilization = 38,790 ÷ 85,000 = 45.635% → `45.6%`
- Rounding: `ROUND_HALF_UP` to 1 decimal for percentages, 2 for duration

### Firm B differences (three config knobs only)

| Metric | Firm A | Firm B | Cause |
|---|---|---|---|
| Aggregate non-IG exposure | 15.0% OK | **21.0% BREACH** | + Marina Bay Resorts (BB, downgraded from BBB-) 6% |
| Largest GRE issuer | 7.0% OK | **13.0% BREACH** | Redhill Power 7% + Redhill Transport 6%, grouped under parent `Redhill Holdings` |
| Utilization format | `58.3%` | `5833 bps` | truncated basis points = `ratio × 10000`, `ROUND_DOWN` |

All other Firm B values are identical to Firm A — but every utilization cell is
re-rendered in bps. This is why computation and presentation must be separate.

---

## 8. Config design (Phase 4 lives or dies here)

`config/firm_a.yaml` and `config/firm_b.yaml` express *method*, not *identity*.
The engine reads knobs; it never reads a firm name.

Required knobs, at minimum:

```yaml
presentation:
  utilization:
    format: percent          # percent | basis_points
    decimals: 1
    rounding: ROUND_HALF_UP  # ROUND_HALF_UP | ROUND_DOWN

figures:
  aggregate_non_ig:
    include:
      - match: {field: asset_class, in: ["High Yield Bonds", "Structured Credit"]}
      # firm_b adds:
      # - match: {field: credit_rating, below_investment_grade: true}

  gre_concentration:
    filter: {field: issuer_type, equals: GRE}
    group_by: issuer_name    # firm_b: parent_issuer
    limit_ref: gre_issuer_cap
```

The shape above is a starting point — refine it, but keep the principle:
**a new firm is a new YAML file, never a code change.**

Validate every config with pydantic. An invalid config must fail loudly at
load time, never produce a silently wrong number.

---

## 9. Where the LLM is allowed

| Zone | LLM? | What |
|---|---|---|
| PDF chunking, CSV loading | No | deterministic parsing |
| Numeric limit extraction | **No** — use regex/table parsing | the guidelines tables are structured; parse them |
| Non-numeric entity extraction (breach actions, owners, retention) | Yes, gated | must return a verbatim span the code verifies exists in the chunk, plus a confidence score; a human gate approves before the graph is trusted |
| Figure computation | **Never** | |
| Narrative commentary | Yes | receives only computed figures — never the raw CSV or PDF |
| Firewall check | No | deterministic token comparison |

Ingestion runs **once** and freezes `artifacts/graph.json` with a content hash.
Report generation reads the frozen graph and makes no LLM call — this is what
keeps constraint 1 true despite LLM non-determinism.

### Firewall implementation
Extract every numeric token from the narrative, normalise it, and compare
against the set of numeric tokens present in the computed figures. Whitelist
non-figure numbers (years like `2024`, section numbers like `4.2`, durations
like `24 hours`, `5 business days`). Any leftover token → reject the narrative.

---

## 10. Style

- English for all code, comments, docstrings, and documentation.
- Type hints on public functions.
- Small modules with clear boundaries — the directory structure is itself an
  argument in the RFC, so keep it honest.
- No cleverness. This code will be read by an auditor-minded reviewer.
- Prefer explicit over implicit, especially around rounding and ordering.

---

## 11. Definition of done

- [ ] `pip install -r requirements.txt && python -m src.main run --firm A` works from clean clone
- [ ] `evaluate --firm A` shows 13/13 figures reconciled
- [ ] `evaluate --firm B` shows Firm B's three differences and matches the brief
- [ ] `verify-determinism` shows identical hashes across two runs
- [ ] `trace <figure>` prints a real path ending at a PDF page + chunk
- [ ] Running with `ANTHROPIC_API_KEY` unset still produces identical figures
- [ ] `pytest` passes, including the no-LLM-import test and the append-only test
- [ ] `docs/01`, `docs/02`, `docs/03` written and consistent with the code
- [ ] `grep -r '"A"\|"B"\|firm_a\|firm_b' src/compute src/graph` returns nothing
