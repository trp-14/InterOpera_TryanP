from pathlib import Path

import pytest

from src.compute.figures import compute_all_figures
from src.compute.formatters import render_all
from src.config.loader import load_config
from src.graph.builder import build_graph

ROOT = Path(__file__).resolve().parents[1]

# CLAUDE.md section 7 ground truth for Firm A.
EXPECTED_FIRM_A = {
    "sgs_allocation": ("35.0%", "OK", "20–60%", "58.3%"),
    "mas_bills_allocation": ("8.0%", "OK", "0–40%", "20.0%"),
    "ig_corporate_allocation": ("33.0%", "OK", "10–50%", "66.0%"),
    "high_yield_allocation": ("9.0%", "OK", "0–15%", "60.0%"),
    "fx_bonds_allocation": ("5.0%", "OK", "0–20%", "25.0%"),
    "structured_credit_allocation": ("6.0%", "OK", "0–10%", "60.0%"),
    "cash_allocation": ("4.0%", "BREACH", "min 5%", "n/a"),
    "aggregate_non_ig": ("15.0%", "OK", "max 20%", "75.0%"),
    "single_issuer_concentration": ("8.0%", "AT LIMIT", "max 8%", "100.0%"),
    "gre_concentration": ("7.0%", "OK", "max 12%", "58.3%"),
    "liquidity_ratio": ("47.0%", "OK", "min 25%", "188.0%"),
    "portfolio_duration": ("3.88 yrs", "OK", "2.0–6.5 yrs", "n/a"),
    "portfolio_dv01": ("SGD 38,790 / bp", "OK", "max 85,000", "45.6%"),
}


@pytest.fixture(scope="module")
def firm_a_report() -> dict:
    graph = build_graph(ROOT / "sample_docs" / "sample_fund_guidelines.pdf", ROOT / "sample_docs" / "sample_holdings.csv")
    config = load_config(ROOT / "config" / "firm_a.yaml")
    results = compute_all_figures(graph, config)
    rendered = render_all(results, config)
    return {r["figure"]: r for r in rendered}


@pytest.mark.parametrize("figure_name", list(EXPECTED_FIRM_A))
def test_figure_matches_ground_truth(firm_a_report, figure_name):
    expected_value, expected_status, expected_limit, expected_utilization = EXPECTED_FIRM_A[figure_name]
    actual = firm_a_report[figure_name]

    assert actual["status"] != "ERROR", f"{figure_name} errored: {actual.get('error')}"
    assert actual["value"] == expected_value
    assert actual["status"] == expected_status
    assert actual["limit"] == expected_limit
    assert actual["utilization"] == expected_utilization


def test_all_13_figures_present(firm_a_report):
    assert set(firm_a_report) == set(EXPECTED_FIRM_A)


def test_every_figure_has_a_real_citation(firm_a_report):
    for name, result in firm_a_report.items():
        assert result["citation"] is not None, f"{name} has no citation"
        assert result["citation"]["source_doc"] == "sample_fund_guidelines.pdf"
        assert result["citation"]["page"] in (1, 2)
        assert result["graph_path"], f"{name} has an empty graph_path"
