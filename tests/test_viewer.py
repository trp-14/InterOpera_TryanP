from pathlib import Path

import pytest

from src.compute.figures import compute_all_figures
from src.compute.formatters import render_all
from src.config.loader import load_config
from src.graph.builder import build_graph
from src.reconcile import compare, viewer

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def firm_a_payload() -> dict:
    graph = build_graph(ROOT / "sample_docs" / "sample_fund_guidelines.pdf", ROOT / "sample_docs" / "sample_holdings.csv")
    config = load_config(ROOT / "config" / "firm_a.yaml")
    reports = render_all(compute_all_figures(graph, config), config)
    return {"run_id": "run_test", "firm": "A", "figures": reports, "narrative": ""}


@pytest.fixture(scope="module")
def answer_key() -> dict:
    return compare.read_answer_key(ROOT / "sample_docs" / "firm_A_answer_key.xlsx")


def test_viewer_html_is_self_contained(firm_a_payload, answer_key):
    html_content = viewer.build_viewer_html(firm_a_payload, answer_key, run_id="run_test", firm_label="Firm A")

    assert html_content.startswith("<!doctype html>")
    assert "<script" not in html_content  # no JS at all - it's pure static markup
    assert "http://" not in html_content and "https://" not in html_content  # no external resources


def test_viewer_html_contains_every_figure(firm_a_payload, answer_key):
    html_content = viewer.build_viewer_html(firm_a_payload, answer_key, run_id="run_test", firm_label="Firm A")
    for fig in firm_a_payload["figures"]:
        assert fig["figure"] in html_content


def test_viewer_shows_match_for_correct_firm_a_run(firm_a_payload, answer_key):
    html_content = viewer.build_viewer_html(firm_a_payload, answer_key, run_id="run_test", firm_label="Firm A")
    assert html_content.count('class="delta match"') == 13
    assert 'class="delta mismatch"' not in html_content


def test_viewer_shows_mismatch_when_figure_disagrees_with_reference():
    payload = {
        "run_id": "run_test", "firm": "A",
        "figures": [{"figure": "cash_allocation", "value": "99.0%", "status": "OK", "limit": "min 5%", "utilization": "n/a", "graph_path": "...", "citation": None, "rule": ""}],
        "narrative": "",
    }
    reference = {"cash_allocation": {"value": "4.0%", "status": "BREACH", "limit": "min 5%"}}
    html_content = viewer.build_viewer_html(payload, reference, run_id="run_test", firm_label="Firm A")
    assert 'class="delta mismatch"' in html_content
    assert "expected 4.0% (BREACH), got 99.0% (OK)" in html_content


def test_viewer_handles_error_status_figure_gracefully():
    payload = {
        "run_id": "run_test", "firm": "A",
        "figures": [{"figure": "broken_figure", "status": "ERROR", "error": "no traceable path to source"}],
        "narrative": "",
    }
    html_content = viewer.build_viewer_html(payload, {}, run_id="run_test", firm_label="Firm A")
    assert "no traceable path to source" in html_content
    assert 'class="status error"' in html_content


def test_viewer_escapes_html_in_narrative_and_citation():
    payload = {
        "run_id": "run_test", "firm": "A",
        "figures": [{
            "figure": "cash_allocation", "value": "4.0%", "status": "BREACH", "limit": "min 5%", "utilization": "n/a",
            "graph_path": "<script>alert(1)</script>",
            "citation": {"source_doc": "x.pdf", "page": 1, "chunk_id": "c1", "passage_summary": "<b>bold</b>"},
            "rule": "",
        }],
        "narrative": "<script>alert('narrative')</script>",
    }
    html_content = viewer.build_viewer_html(payload, {}, run_id="run_test", firm_label="Firm A")
    assert "<script>alert(1)</script>" not in html_content
    assert "<script>alert('narrative')</script>" not in html_content
    assert "&lt;script&gt;" in html_content
