"""CLI entry point for the Meridian Fixed Income Fund compliance pipeline.

Subcommands are stubs until their BUILD_PLAN.md step is implemented.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path

from src.audit import log as audit_log
from src.compute import excel_report
from src.compute.figures import compute_all_figures
from src.compute.formatters import render_all
from src.config.loader import ConfigError, config_content_hash, load_config
from src.graph import builder, schema
from src.narrative.firewall import check_narrative
from src.narrative.generator import generate_narrative
from src.reconcile import compare, report, viewer

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GUIDELINES_PDF = PROJECT_ROOT / "sample_docs" / "sample_fund_guidelines.pdf"
HOLDINGS_CSV = PROJECT_ROOT / "sample_docs" / "sample_holdings.csv"
REPORT_TEMPLATE = PROJECT_ROOT / "sample_docs" / "report_template.xlsx"
GRAPH_PATH = PROJECT_ROOT / "artifacts" / "graph.json"
GRAPH_REVIEW_PATH = PROJECT_ROOT / "artifacts" / "graph_review.json"
AUDIT_DB_PATH = PROJECT_ROOT / "audit.db"

# The only place a firm name selects a file — the engine (src/compute,
# src/graph, src/ingestion) never sees "A"/"B" (CLAUDE.md section 3.1).
_CONFIG_FILENAME = {"A": "firm_a.yaml", "B": "firm_b.yaml"}


def cmd_ingest(args: argparse.Namespace) -> None:
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    print(f"Run ID: {run_id}")

    graph = builder.build_graph(GUIDELINES_PDF, HOLDINGS_CSV)
    content_hash = builder.freeze_graph(graph, GRAPH_PATH)
    print(f"Built graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    print(f"Froze to {GRAPH_PATH.relative_to(PROJECT_ROOT)} (content_hash={content_hash})")

    conn = audit_log.connect(AUDIT_DB_PATH)
    try:
        audit_log.append_event(
            conn, run_id=run_id, event_type="graph_built", actor="system",
            payload={
                "content_hash": content_hash,
                "node_count": graph.number_of_nodes(),
                "edge_count": graph.number_of_edges(),
            },
        )

        review = builder.find_review_needed(graph)

        if args.auto_approve:
            audit_log.append_event(
                conn, run_id=run_id, event_type="graph_approved", actor="system",
                payload={"method": "auto-approve", "review_items_skipped": len(review)},
            )
            print(f"Graph auto-approved (--auto-approve). {len(review)} item(s) needing review were skipped.")
        elif review:
            GRAPH_REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
            GRAPH_REVIEW_PATH.write_text(
                json.dumps(review, indent=2, sort_keys=True, default=builder.json_default), encoding="utf-8"
            )
            print(f"{len(review)} node(s) need human review -> {GRAPH_REVIEW_PATH.relative_to(PROJECT_ROOT)}")
            print(f"After reviewing, run: python -m src.main approve-graph --run-id {run_id}")
        else:
            audit_log.append_event(
                conn, run_id=run_id, event_type="graph_approved", actor="system",
                payload={"method": "auto-pass", "reason": f"all nodes >= {schema.HUMAN_REVIEW_CONFIDENCE_THRESHOLD} confidence"},
            )
            print(f"All nodes >= {schema.HUMAN_REVIEW_CONFIDENCE_THRESHOLD} confidence; graph auto-passed, no review needed.")
    finally:
        conn.close()


def cmd_approve_graph(args: argparse.Namespace) -> None:
    if not GRAPH_PATH.exists():
        raise SystemExit(f"no frozen graph at {GRAPH_PATH.relative_to(PROJECT_ROOT)} - run `ingest` first")

    conn = audit_log.connect(AUDIT_DB_PATH)
    try:
        if not audit_log.has_event(conn, args.run_id, "graph_built"):
            raise SystemExit(f"no graph_built event found for run_id={args.run_id!r} - check the id from `ingest`")

        reviewed_items = 0
        if GRAPH_REVIEW_PATH.exists():
            reviewed_items = len(json.loads(GRAPH_REVIEW_PATH.read_text(encoding="utf-8")))

        audit_log.append_event(
            conn, run_id=args.run_id, event_type="graph_approved", actor="human",
            payload={"method": "manual", "reviewed_items": reviewed_items},
        )
        print(f"Graph for run_id={args.run_id} approved ({reviewed_items} reviewed item(s) recorded).")
    finally:
        conn.close()


def cmd_run(args: argparse.Namespace) -> None:
    if not GRAPH_PATH.exists():
        raise SystemExit(f"no frozen graph at {GRAPH_PATH.relative_to(PROJECT_ROOT)} - run `ingest` first")

    config_path = PROJECT_ROOT / "config" / _CONFIG_FILENAME[args.firm]
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    print(f"Run ID: {run_id}")

    # Reads the frozen graph only — never re-ingests, never calls an LLM
    # (CLAUDE.md section 9: this is what keeps `run` deterministic).
    graph = builder.load_frozen_graph(GRAPH_PATH)

    conn = audit_log.connect(AUDIT_DB_PATH)
    try:
        audit_log.append_event(
            conn, run_id=run_id, event_type="config_loaded", actor="system",
            payload={
                "path": _CONFIG_FILENAME[args.firm],
                "content_hash": config_content_hash(config_path),
                "label": config.label,
            },
        )

        results = compute_all_figures(graph, config)
        for result in results:
            audit_log.append_event(
                conn, run_id=run_id, event_type="figure_computed", actor="system",
                payload={"figure": result.figure, "status": result.status},
            )

        reports = render_all(results, config)

        output_dir = PROJECT_ROOT / "artifacts" / run_id
        report_path = output_dir / f"report_firm_{args.firm}.xlsx"
        excel_report.write_report(REPORT_TEMPLATE, reports, report_path)

        # Narrative receives ONLY the already-computed, already-formatted
        # figures - never the CSV/PDF (CLAUDE.md section 9). Returns None
        # with no API key, which is exactly what keeps figures complete and
        # identical either way (section 3.2's acceptance test).
        narrative = generate_narrative(reports)
        if narrative is not None:
            audit_log.append_event(
                conn, run_id=run_id, event_type="narrative_generated", actor="llm",
                payload={"length": len(narrative)},
            )
            firewall_result = check_narrative(narrative, reports)
            audit_log.append_event(
                conn, run_id=run_id, event_type="firewall_checked", actor="system",
                payload={"passed": firewall_result.passed, "rejected_tokens": firewall_result.rejected_tokens},
            )
            if not firewall_result.passed:
                print(f"WARNING: narrative rejected by firewall (unexplained numbers: {firewall_result.rejected_tokens}) - omitted")
                narrative = None

        figures_path = output_dir / "figures.json"
        figures_path.write_text(
            json.dumps(
                {"run_id": run_id, "firm": args.firm, "figures": reports, "narrative": narrative or ""},
                indent=2, sort_keys=True, ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        audit_log.append_event(
            conn, run_id=run_id, event_type="report_exported", actor="system",
            payload={"report_path": str(report_path.relative_to(PROJECT_ROOT)), "figures_path": str(figures_path.relative_to(PROJECT_ROOT))},
        )

        print(f"Wrote {report_path.relative_to(PROJECT_ROOT)}")
        print(f"Wrote {figures_path.relative_to(PROJECT_ROOT)}")
        if narrative is None:
            print("Narrative: empty (no ANTHROPIC_API_KEY, or rejected by firewall)")

        error_count = sum(1 for r in results if r.status == "ERROR")
        if error_count:
            print(f"WARNING: {error_count} figure(s) could not be computed (status=ERROR) - see {figures_path.name}")
    finally:
        conn.close()


def cmd_evaluate(args: argparse.Namespace) -> None:
    if not GRAPH_PATH.exists():
        raise SystemExit(f"no frozen graph at {GRAPH_PATH.relative_to(PROJECT_ROOT)} - run `ingest` first")

    config_path = PROJECT_ROOT / "config" / _CONFIG_FILENAME[args.firm]
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc

    graph = builder.load_frozen_graph(GRAPH_PATH)
    results = compute_all_figures(graph, config)
    reports = render_all(results, config)

    answer_key = compare.read_answer_key(PROJECT_ROOT / "sample_docs" / "firm_A_answer_key.xlsx")
    reference = answer_key if args.firm == "A" else compare.firm_b_reference(answer_key)

    reconciliation_rows = compare.reconcile(reports, reference)
    recon_ok = report.print_reconciliation(reconciliation_rows)
    trace_ok = report.print_traceability(reports)

    narrative = generate_narrative(reports) or ""
    firewall_ok = report.print_firewall(narrative, reports)

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    conn = audit_log.connect(AUDIT_DB_PATH)
    try:
        audit_log.append_event(
            conn, run_id=run_id, event_type="reconciliation_run", actor="system",
            payload={
                "firm": args.firm,
                "reconciled": sum(1 for r in reconciliation_rows if r.passed),
                "total": len(reconciliation_rows),
                "traceability_passed": trace_ok,
                "firewall_passed": firewall_ok,
            },
        )
    finally:
        conn.close()

    print("\n=== Summary ===")
    print(f"Reconciliation: {'PASS' if recon_ok else 'FAIL'}")
    print(f"Traceability:   {'PASS' if trace_ok else 'FAIL'}")
    print(f"Firewall:       {'PASS' if firewall_ok else 'FAIL'}")

    if not (recon_ok and trace_ok and firewall_ok):
        raise SystemExit(1)


def cmd_trace(args: argparse.Namespace) -> None:
    if not GRAPH_PATH.exists():
        raise SystemExit(f"no frozen graph at {GRAPH_PATH.relative_to(PROJECT_ROOT)} - run `ingest` first")

    config_path = PROJECT_ROOT / "config" / _CONFIG_FILENAME[args.firm]
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc

    graph = builder.load_frozen_graph(GRAPH_PATH)
    results = compute_all_figures(graph, config)

    matches = [r for r in results if r.figure == args.figure_name]
    if not matches:
        valid_names = ", ".join(sorted(r.figure for r in results))
        raise SystemExit(f"unknown figure {args.figure_name!r}. Valid names: {valid_names}")

    result = matches[0]
    print(f"figure:     {result.figure}")
    if result.status == "ERROR":
        print(f"status:     ERROR - {result.error}")
        return

    print(f"value:      {result.value} {result.unit}")
    print(f"status:     {result.status}")
    print(f"limit:      min={result.limit_min} max={result.limit_max}")
    print(f"graph_path: {result.graph_path}")
    if result.citation:
        print(f"source:     {result.citation.source_doc} p.{result.citation.page} (chunk {result.citation.chunk_id})")
        print(f"passage:    {result.citation.passage_summary}")


def cmd_verify_determinism(args: argparse.Namespace) -> None:
    if not GRAPH_PATH.exists():
        raise SystemExit(f"no frozen graph at {GRAPH_PATH.relative_to(PROJECT_ROOT)} - run `ingest` first")

    config_path = PROJECT_ROOT / "config" / _CONFIG_FILENAME[args.firm]
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc

    def _run_once() -> str:
        graph = builder.load_frozen_graph(GRAPH_PATH)
        reports = render_all(compute_all_figures(graph, config), config)
        payload = json.dumps(reports, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    hash1 = _run_once()
    hash2 = _run_once()

    print(f"run 1 hash: {hash1}")
    print(f"run 2 hash: {hash2}")
    if hash1 == hash2:
        print("PASS: figures are identical across runs")
    else:
        raise SystemExit("FAIL: figures differ across runs - determinism broken")


def cmd_viewer(args: argparse.Namespace) -> None:
    """Bonus (BUILD_PLAN.md Step 13): write a self-contained viewer.html
    from an already-completed run's artifacts. Reads figures.json and the
    answer key only — never recomputes a figure."""
    artifacts_dir = PROJECT_ROOT / "artifacts"

    if args.run_id:
        run_dir = artifacts_dir / args.run_id
        if not (run_dir / "figures.json").exists():
            raise SystemExit(f"no figures.json at artifacts/{args.run_id}/ - run `run --firm A|B` first")
    else:
        candidates = sorted(
            (d for d in artifacts_dir.iterdir() if d.is_dir() and (d / "figures.json").exists()),
            key=lambda d: (d / "figures.json").stat().st_mtime,
        )
        if not candidates:
            raise SystemExit("no run artifacts found under artifacts/ - run `run --firm A|B` first")
        run_dir = candidates[-1]

    payload = json.loads((run_dir / "figures.json").read_text(encoding="utf-8"))
    firm = payload.get("firm", "A")

    answer_key = compare.read_answer_key(PROJECT_ROOT / "sample_docs" / "firm_A_answer_key.xlsx")
    reference = answer_key if firm == "A" else compare.firm_b_reference(answer_key)

    html_content = viewer.build_viewer_html(payload, reference, run_id=run_dir.name, firm_label=f"Firm {firm}")
    viewer_path = run_dir / "viewer.html"
    viewer_path.write_text(html_content, encoding="utf-8")
    print(f"Wrote {viewer_path.relative_to(PROJECT_ROOT)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.main",
        description="Auditable portfolio compliance report pipeline for Meridian Fixed Income Fund.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_ingest = subparsers.add_parser("ingest", help="build graph, freeze to artifacts/graph.json")
    p_ingest.add_argument("--auto-approve", action="store_true", help="skip the human gate for demo runs")
    p_ingest.set_defaults(func=cmd_ingest)

    p_approve = subparsers.add_parser("approve-graph", help="human gate: approve a frozen graph")
    p_approve.add_argument("--run-id", required=True)
    p_approve.set_defaults(func=cmd_approve_graph)

    p_run = subparsers.add_parser("run", help="produce report for a firm")
    p_run.add_argument("--firm", required=True, choices=["A", "B"])
    p_run.set_defaults(func=cmd_run)

    p_evaluate = subparsers.add_parser("evaluate", help="reconcile + traceability + firewall")
    p_evaluate.add_argument("--firm", required=True, choices=["A", "B"])
    p_evaluate.set_defaults(func=cmd_evaluate)

    p_trace = subparsers.add_parser("trace", help="print one figure's path to source")
    p_trace.add_argument("figure_name")
    p_trace.add_argument("--firm", choices=["A", "B"], default="A", help="which firm's config to use (default: A)")
    p_trace.set_defaults(func=cmd_trace)

    p_verify = subparsers.add_parser("verify-determinism", help="run twice, compare hashes")
    p_verify.add_argument("--firm", required=True, choices=["A", "B"])
    p_verify.set_defaults(func=cmd_verify_determinism)

    p_viewer = subparsers.add_parser("viewer", help="write a self-contained viewer.html from a run's artifacts (bonus)")
    p_viewer.add_argument("--run-id", help="which run to view (default: most recently written)")
    p_viewer.set_defaults(func=cmd_viewer)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
