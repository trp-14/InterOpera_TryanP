from pathlib import Path

import pytest

from src.compute.figures import compute_all_figures
from src.compute.formatters import render_all
from src.config.loader import load_config
from src.graph.builder import build_graph
from src.reconcile import compare, report

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def graph():
    return build_graph(ROOT / "sample_docs" / "sample_fund_guidelines.pdf", ROOT / "sample_docs" / "sample_holdings.csv")


@pytest.fixture(scope="module")
def answer_key() -> dict:
    return compare.read_answer_key(ROOT / "sample_docs" / "firm_A_answer_key.xlsx")


def test_firm_a_reconciles_13_of_13(graph, answer_key):
    config = load_config(ROOT / "config" / "firm_a.yaml")
    reports = render_all(compute_all_figures(graph, config), config)

    rows = compare.reconcile(reports, answer_key)
    assert sum(1 for r in rows if r.passed) == 13
    assert len(rows) == 13


def test_firm_b_reconciles_13_of_13_against_derived_reference(graph, answer_key):
    config = load_config(ROOT / "config" / "firm_b.yaml")
    reports = render_all(compute_all_figures(graph, config), config)

    reference = compare.firm_b_reference(answer_key)
    rows = compare.reconcile(reports, reference)
    assert sum(1 for r in rows if r.passed) == 13


def test_firm_a_fully_traceable(graph, capsys):
    config = load_config(ROOT / "config" / "firm_a.yaml")
    reports = render_all(compute_all_figures(graph, config), config)
    assert report.print_traceability(reports) is True


def test_clean_narrative_passes_firewall_check(capsys):
    reports = [{"figure": "cash_allocation", "value": "4.0%", "status": "BREACH", "limit": "min 5%", "utilization": "n/a", "citation": {}}]
    assert report.print_firewall("Cash allocation is 4.0%, a BREACH against min 5%.", reports) is True


def test_dirty_narrative_fails_firewall_check(capsys):
    reports = [{"figure": "cash_allocation", "value": "4.0%", "status": "BREACH", "limit": "min 5%", "utilization": "n/a", "citation": {}}]
    assert report.print_firewall("Cash allocation is 4.0%, projected to recover to 12.7% next quarter.", reports) is False


def test_determinism_two_independent_runs_produce_identical_output(graph):
    config = load_config(ROOT / "config" / "firm_a.yaml")
    run1 = render_all(compute_all_figures(graph, config), config)
    run2 = render_all(compute_all_figures(graph, config), config)
    assert run1 == run2
