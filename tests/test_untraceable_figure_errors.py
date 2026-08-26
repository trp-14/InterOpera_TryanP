"""An untraceable figure must come back as an ERROR record, never a bare
value (BUILD_PLAN.md Step 10 / CLAUDE.md section 3.5)."""
from __future__ import annotations

from pathlib import Path

from src.compute.figures import FigureResult, compute_all_figures
from src.compute.formatters import to_report_dict
from src.config.loader import load_config
from src.graph.builder import build_graph

ROOT = Path(__file__).resolve().parents[1]


def test_untraceable_figure_becomes_error_not_a_bare_value():
    graph = build_graph(ROOT / "sample_docs" / "sample_fund_guidelines.pdf", ROOT / "sample_docs" / "sample_holdings.csv")
    config = load_config(ROOT / "config" / "firm_a.yaml")

    # Simulate a broken citation: point the SGS limit's chunk_id at a chunk
    # that doesn't exist in the graph, so the figure can't be traced to a
    # source chunk anymore.
    graph.nodes["limit:sgs_allocation"]["chunk_id"] = "chunk_does_not_exist"

    results = compute_all_figures(graph, config)
    sgs_result = next(r for r in results if r.figure == "sgs_allocation")

    assert sgs_result.status == "ERROR"
    assert sgs_result.value is None
    assert sgs_result.citation is None
    assert sgs_result.error

    # One untraceable figure doesn't take down the whole run.
    assert len(results) == 13
    other_results = [r for r in results if r.figure != "sgs_allocation"]
    assert all(r.status != "ERROR" for r in other_results)


def test_error_figure_json_shape_matches_spec():
    """CLAUDE.md section 3.5's exact required shape:
    {"figure": "...", "status": "ERROR", "error": "..."} - no value, limit,
    utilization, graph_path, or citation key."""
    error_result = FigureResult(
        figure="some_figure", status="ERROR", unit="", value=None,
        limit_min=None, limit_max=None, limit_display_mode="none",
        utilization=None, graph_path="", citation=None,
        error="no traceable path to source",
    )
    assert to_report_dict(error_result) == {
        "figure": "some_figure",
        "status": "ERROR",
        "error": "no traceable path to source",
    }


def test_missing_asset_class_node_also_errors_gracefully():
    graph = build_graph(ROOT / "sample_docs" / "sample_fund_guidelines.pdf", ROOT / "sample_docs" / "sample_holdings.csv")
    config = load_config(ROOT / "config" / "firm_a.yaml")

    graph.remove_node("assetclass:sgs")

    results = compute_all_figures(graph, config)
    sgs_result = next(r for r in results if r.figure == "sgs_allocation")
    assert sgs_result.status == "ERROR"
    assert sgs_result.error
