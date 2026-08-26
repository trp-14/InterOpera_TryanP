# Architecture

## Layers

Six layers, each a Python package under `src/`, plus the audit log. Layer
packages never touch the audit log themselves — `src/main.py`'s CLI commands
are the only code that imports `src.audit`, orchestrating each layer in turn
and recording what happened after each step. Arrows follow the direction
data actually flows at runtime, not import direction.

```mermaid
flowchart TB
    subgraph Sources["sample_docs/ (read-only inputs)"]
        PDF["sample_fund_guidelines.pdf"]
        CSV["sample_holdings.csv"]
        AnswerKey["firm_A_answer_key.xlsx"]
        Template["report_template.xlsx"]
    end

    subgraph Ingestion["src/ingestion — zero LLM"]
        PdfParser["pdf_parser.py\nregex/table extraction"]
        CsvLoader["csv_loader.py"]
        Chunker["chunker.py"]
    end

    subgraph Graph["src/graph — zero LLM"]
        Builder["builder.py\nbuild_graph / freeze_graph / load_frozen_graph"]
        FrozenGraph[("artifacts/graph.json\n(content-hashed)")]
    end

    subgraph Config["src/config"]
        FirmYaml["config/firm_a.yaml\nconfig/firm_b.yaml"]
        Loader["loader.py (pydantic validation)"]
    end

    subgraph Compute["src/compute — zero LLM"]
        Figures["figures.py\n13 figures, graph traversal, Decimal"]
        Formatters["formatters.py\npresentation only"]
        Excel["excel_report.py"]
    end

    subgraph Narrative["src/narrative — ONLY LLM-allowed package"]
        Generator["generator.py\nClaude, figures JSON in, prose out"]
        Firewall["firewall.py\ndeterministic token check"]
    end

    subgraph Reconcile["src/reconcile"]
        Compare["compare.py\ndiff vs answer key"]
        Report["report.py\nprint 3 checks"]
    end

    CLI["src/main.py\ningest / run / evaluate / trace CLI commands"]
    Audit[("audit.db\nappend-only, hash-chained")]

    PDF --> PdfParser
    PDF --> Chunker
    CSV --> CsvLoader
    PdfParser --> Builder
    CsvLoader --> Builder
    Chunker --> Builder
    Builder --> FrozenGraph
    FrozenGraph --> Figures
    FirmYaml --> Loader --> Figures
    Figures --> Formatters
    Formatters --> Excel
    Template --> Excel
    Formatters --> Generator
    Generator -.LLM call - figures JSON only.-> Firewall
    Firewall --> Reports[["figures.json\n{figures, narrative}"]]
    Excel --> ExcelOut[("report_firm_X.xlsx")]
    Formatters --> Compare
    AnswerKey --> Compare
    Compare --> Report

    CLI --> Ingestion
    CLI --> Graph
    CLI --> Config
    CLI --> Compute
    CLI --> Narrative
    CLI --> Reconcile
    CLI -.writes after every step.-> Audit
```

## Where the LLM may and may not appear

`anthropic` is imported in exactly one file in the whole project:
`src/narrative/generator.py`. `tests/test_no_llm_in_compute.py` parses the
AST of every file under `src/compute` and `src/graph` and fails if either
package ever imports `anthropic`, `openai`, `httpx`, or anything under
`src/narrative` — this isn't a convention, it's enforced.

| Layer | LLM allowed? | Why |
|---|---|---|
| Ingestion | No | Numeric limits come from regex/table parsing against a structured PDF. The architecture *supports* LLM-assisted extraction of non-numeric fields (breach-action text, owners) behind the same `extraction_confidence` human-review gate used for everything else — but in this implementation, the guidelines document's breach-action column parses cleanly with regex, so no LLM call actually happens during ingestion. See `docs/03_rfc.md` question 1 for why this matters even when unused. |
| Graph | Never | Pure data assembly from ingestion output. |
| Compute | Never | Every figure is `Decimal` arithmetic over graph traversal results. |
| Reconcile | Never | String comparison against the answer key. |
| Narrative | Yes | The only zone. Receives the already-computed, already-formatted `figures.json` list — never the CSV, the PDF, or the graph. |
| Firewall | No | Deterministic regex token extraction and set comparison, checking the narrative's own output — this specifically must not be another LLM call, or a hallucinated number could be "verified" by a second hallucination. |

## Why the graph sits between ingestion and compute

`run` never re-parses the PDF or CSV — it calls `builder.load_frozen_graph`,
which reads `artifacts/graph.json` and verifies its stored content hash
before trusting it. Ingestion happens once (`ingest`), is gated by a human
when confidence warrants it (`approve-graph`), and every subsequent `run` or
`evaluate` reads that same frozen, approved graph. This is what keeps
constraint 1 (reproducibility) true even though ingestion's non-numeric
extraction path is architecturally allowed to be LLM-assisted (LLMs aren't
deterministic) — by the time `run` executes, ingestion is already finished
and its output is frozen data, not a live process.
