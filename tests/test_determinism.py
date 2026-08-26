"""Two independent runs on the same inputs produce identical output
(BUILD_PLAN.md Step 10 / CLAUDE.md constraint 1)."""
from __future__ import annotations

from pathlib import Path

from src.compute.figures import compute_all_figures
from src.compute.formatters import render_all
from src.config.loader import load_config
from src.graph.builder import build_graph, freeze_graph

ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = ROOT / "sample_docs" / "sample_fund_guidelines.pdf"
CSV_PATH = ROOT / "sample_docs" / "sample_holdings.csv"


def test_graph_content_hash_is_deterministic(tmp_path):
    graph1 = build_graph(PDF_PATH, CSV_PATH)
    graph2 = build_graph(PDF_PATH, CSV_PATH)

    hash1 = freeze_graph(graph1, tmp_path / "g1.json")
    hash2 = freeze_graph(graph2, tmp_path / "g2.json")
    assert hash1 == hash2


def test_firm_a_figures_are_deterministic():
    graph1 = build_graph(PDF_PATH, CSV_PATH)
    graph2 = build_graph(PDF_PATH, CSV_PATH)
    config = load_config(ROOT / "config" / "firm_a.yaml")

    run1 = render_all(compute_all_figures(graph1, config), config)
    run2 = render_all(compute_all_figures(graph2, config), config)
    assert run1 == run2


def test_firm_b_figures_are_deterministic():
    graph1 = build_graph(PDF_PATH, CSV_PATH)
    graph2 = build_graph(PDF_PATH, CSV_PATH)
    config = load_config(ROOT / "config" / "firm_b.yaml")

    run1 = render_all(compute_all_figures(graph1, config), config)
    run2 = render_all(compute_all_figures(graph2, config), config)
    assert run1 == run2


def test_same_graph_computed_twice_is_deterministic():
    """Same in-memory graph object, two separate compute passes - rules out
    any hidden mutable state inside figures.py itself."""
    graph = build_graph(PDF_PATH, CSV_PATH)
    config = load_config(ROOT / "config" / "firm_a.yaml")

    run1 = render_all(compute_all_figures(graph, config), config)
    run2 = render_all(compute_all_figures(graph, config), config)
    assert run1 == run2
