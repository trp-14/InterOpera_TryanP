"""CLI entry point for the Meridian Fixed Income Fund compliance pipeline.

Subcommands are stubs until their BUILD_PLAN.md step is implemented.
"""
from __future__ import annotations

import argparse
import sys


def cmd_ingest(args: argparse.Namespace) -> None:
    raise NotImplementedError("ingest: implemented in BUILD_PLAN.md Step 2/3")


def cmd_approve_graph(args: argparse.Namespace) -> None:
    raise NotImplementedError("approve-graph: implemented in BUILD_PLAN.md Step 3")


def cmd_run(args: argparse.Namespace) -> None:
    raise NotImplementedError("run: implemented in BUILD_PLAN.md Step 5-8")


def cmd_evaluate(args: argparse.Namespace) -> None:
    raise NotImplementedError("evaluate: implemented in BUILD_PLAN.md Step 9")


def cmd_trace(args: argparse.Namespace) -> None:
    raise NotImplementedError("trace: implemented in BUILD_PLAN.md Step 9")


def cmd_verify_determinism(args: argparse.Namespace) -> None:
    raise NotImplementedError("verify-determinism: implemented in BUILD_PLAN.md Step 9")


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
    p_trace.set_defaults(func=cmd_trace)

    p_verify = subparsers.add_parser("verify-determinism", help="run twice, compare hashes")
    p_verify.add_argument("--firm", required=True, choices=["A", "B"])
    p_verify.set_defaults(func=cmd_verify_determinism)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
