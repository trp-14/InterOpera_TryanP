from src.narrative.firewall import check_narrative
from src.narrative.generator import generate_narrative

SAMPLE_FIGURES = [
    {
        "figure": "cash_allocation", "value": "4.0%", "status": "BREACH",
        "limit": "min 5%", "utilization": "n/a", "graph_path": "...", "citation": {},
    },
    {
        "figure": "single_issuer_concentration", "value": "8.0%", "status": "AT LIMIT",
        "limit": "max 8%", "utilization": "100.0%", "graph_path": "...", "citation": {},
    },
    {
        "figure": "portfolio_dv01", "value": "SGD 38,790 / bp", "status": "OK",
        "limit": "max 85,000", "utilization": "45.6%", "graph_path": "...", "citation": {},
    },
]


def test_narrative_using_only_real_numbers_passes():
    text = (
        "Cash allocation stands at 4.0% against a minimum of min 5%, a BREACH. "
        "Single issuer concentration is at 8.0%, right at its max 8% limit."
    )
    result = check_narrative(text, SAMPLE_FIGURES)
    assert result.passed
    assert result.rejected_tokens == []


def test_narrative_with_fabricated_number_is_rejected():
    text = "Cash allocation is 4.0% now, but is projected to recover to 12.7% by next quarter."
    result = check_narrative(text, SAMPLE_FIGURES)
    assert not result.passed
    assert "12.7" in result.rejected_tokens


def test_narrative_with_fabricated_breach_count_is_rejected():
    text = "There were 3 breaches this quarter, most notably cash allocation at 4.0%."
    result = check_narrative(text, SAMPLE_FIGURES)
    assert not result.passed
    assert "3" in result.rejected_tokens


def test_year_is_whitelisted():
    text = "As of 2026, cash allocation is 4.0%."
    assert check_narrative(text, SAMPLE_FIGURES).passed


def test_section_reference_is_whitelisted():
    text = "Per Section 4.2 of the guidelines, cash allocation is 4.0%."
    assert check_narrative(text, SAMPLE_FIGURES).passed


def test_duration_with_unit_is_whitelisted():
    text = "This must be reported within 24 hours and remedied within 5 business days. Cash allocation is 4.0%."
    assert check_narrative(text, SAMPLE_FIGURES).passed


def test_duration_number_without_unit_is_not_whitelisted():
    # "24" alone (no "hours" attached) is not automatically safe - could be a
    # smuggled figure wearing a duration's clothing.
    text = "The number 24 stands alone here. Cash allocation is 4.0%."
    result = check_narrative(text, SAMPLE_FIGURES)
    assert not result.passed
    assert "24" in result.rejected_tokens


def test_figure_name_with_digits_is_not_mistaken_for_a_number():
    # Regression: "DV01" contains digits ("01"), but naming the figure isn't
    # a numeric claim - and the digit shouldn't leak out as a stray "1" either.
    text = "Portfolio DV01 is SGD 38,790 / bp, well within its max 85,000 limit."
    result = check_narrative(text, SAMPLE_FIGURES)
    assert result.passed, result.rejected_tokens


def test_comma_formatted_currency_normalizes_correctly():
    text = "Portfolio DV01 is SGD 38,790 / bp against a limit of max 85,000, giving 45.6% utilization."
    assert check_narrative(text, SAMPLE_FIGURES).passed


def test_error_status_figures_contribute_no_numbers():
    error_figures = [{"figure": "some_figure", "status": "ERROR", "error": "no traceable path to source"}]
    text = "The value is 99.9% today."
    result = check_narrative(text, error_figures)
    assert not result.passed
    assert "99.9" in result.rejected_tokens


def test_empty_narrative_trivially_passes():
    assert check_narrative("", SAMPLE_FIGURES).passed


def test_generate_narrative_returns_none_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert generate_narrative(SAMPLE_FIGURES) is None


def test_generate_narrative_returns_none_with_explicit_empty_key():
    assert generate_narrative(SAMPLE_FIGURES, api_key="") is None
