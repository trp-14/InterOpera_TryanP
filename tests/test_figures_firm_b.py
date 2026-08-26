from pathlib import Path

import pytest

from src.compute.figures import compute_all_figures
from src.compute.formatters import render_all
from src.config.loader import load_config
from src.graph.builder import build_graph

ROOT = Path(__file__).resolve().parents[1]

# firm_B_brief.md / CLAUDE.md section 7: only these three figures differ from
# Firm A. Everything else must be identical.
EXPECTED_FIRM_B_DIFFERENCES = {
    "aggregate_non_ig": ("21.0%", "BREACH", "max 20%", "10500 bps"),
    "gre_concentration": ("13.0%", "BREACH", "max 12%", "10833 bps"),
}

FIGURES_UNCHANGED_FROM_FIRM_A = (
    "sgs_allocation", "mas_bills_allocation", "ig_corporate_allocation", "high_yield_allocation",
    "fx_bonds_allocation", "structured_credit_allocation", "cash_allocation",
    "single_issuer_concentration", "liquidity_ratio", "portfolio_duration", "portfolio_dv01",
)


@pytest.fixture(scope="module")
def graph():
    return build_graph(ROOT / "sample_docs" / "sample_fund_guidelines.pdf", ROOT / "sample_docs" / "sample_holdings.csv")


@pytest.fixture(scope="module")
def firm_a_report(graph) -> dict:
    config = load_config(ROOT / "config" / "firm_a.yaml")
    return {r["figure"]: r for r in render_all(compute_all_figures(graph, config), config)}


@pytest.fixture(scope="module")
def firm_b_report(graph) -> dict:
    config = load_config(ROOT / "config" / "firm_b.yaml")
    return {r["figure"]: r for r in render_all(compute_all_figures(graph, config), config)}


@pytest.mark.parametrize("figure_name", list(EXPECTED_FIRM_B_DIFFERENCES))
def test_firm_b_difference_matches_brief(firm_b_report, figure_name):
    expected_value, expected_status, expected_limit, expected_utilization = EXPECTED_FIRM_B_DIFFERENCES[figure_name]
    actual = firm_b_report[figure_name]
    assert actual["value"] == expected_value
    assert actual["status"] == expected_status
    assert actual["limit"] == expected_limit
    assert actual["utilization"] == expected_utilization


def test_firm_b_utilization_always_in_bps(firm_b_report):
    for name, result in firm_b_report.items():
        if result["utilization"] != "n/a":
            assert result["utilization"].endswith(" bps"), f"{name}: {result['utilization']!r} is not bps"


@pytest.mark.parametrize("figure_name", FIGURES_UNCHANGED_FROM_FIRM_A)
def test_figure_value_and_status_unchanged_from_firm_a(firm_a_report, firm_b_report, figure_name):
    a, b = firm_a_report[figure_name], firm_b_report[figure_name]
    assert a["value"] == b["value"]
    assert a["status"] == b["status"]
    assert a["limit"] == b["limit"]


def test_only_the_three_documented_knobs_changed(firm_a_report, firm_b_report):
    """Every figure's utilization format differs (percent vs bps, by design),
    but value/status/limit must differ *only* for the two documented figures."""
    changed_value_or_status = {
        name
        for name in firm_a_report
        if (firm_a_report[name]["value"], firm_a_report[name]["status"]) != (firm_b_report[name]["value"], firm_b_report[name]["status"])
    }
    assert changed_value_or_status == set(EXPECTED_FIRM_B_DIFFERENCES)
