import pytest

from src.config.loader import ConfigError, load_config


def test_firm_a_config_loads():
    config = load_config("config/firm_a.yaml")
    assert config.presentation.utilization.format == "percent"
    assert config.presentation.utilization.rounding == "ROUND_HALF_UP"


def test_firm_b_config_loads():
    config = load_config("config/firm_b.yaml")
    assert config.presentation.utilization.format == "basis_points"
    assert config.presentation.utilization.rounding == "ROUND_DOWN"


def test_firm_a_and_firm_b_differ_only_in_expected_places():
    a = load_config("config/firm_a.yaml")
    b = load_config("config/firm_b.yaml")

    assert a.presentation.utilization != b.presentation.utilization
    assert a.figures["aggregate_non_ig"] != b.figures["aggregate_non_ig"]
    assert a.figures["gre_concentration"].group_by != b.figures["gre_concentration"].group_by

    assert a.presentation.percentage == b.presentation.percentage
    assert a.presentation.duration == b.presentation.duration
    assert a.figures["liquidity_ratio"] == b.figures["liquidity_ratio"]
    assert a.figures["single_issuer_concentration"] == b.figures["single_issuer_concentration"]


def _write(tmp_path, name: str, content: str):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


_VALID_PRESENTATION = """
presentation:
  utilization: {format: percent, decimals: 1, rounding: ROUND_HALF_UP}
  percentage: {decimals: 1, rounding: ROUND_HALF_UP}
  duration: {decimals: 2, rounding: ROUND_HALF_UP}
  currency: {decimals: 0, rounding: ROUND_HALF_UP}
"""


def test_broken_enum_value_rejected_with_field_name(tmp_path):
    broken = _write(
        tmp_path,
        "broken.yaml",
        f"""
label: "Broken Firm"
presentation:
  utilization: {{format: not_a_real_format, decimals: 1, rounding: ROUND_HALF_UP}}
  percentage: {{decimals: 1, rounding: ROUND_HALF_UP}}
  duration: {{decimals: 2, rounding: ROUND_HALF_UP}}
  currency: {{decimals: 0, rounding: ROUND_HALF_UP}}
figures: {{}}
""",
    )
    with pytest.raises(ConfigError) as exc_info:
        load_config(broken)
    assert "format" in str(exc_info.value)


def test_field_match_with_no_predicate_rejected(tmp_path):
    broken = _write(
        tmp_path,
        "broken_match.yaml",
        f"""
label: "Broken Firm"
{_VALID_PRESENTATION}
figures:
  aggregate_non_ig:
    kind: aggregate
    include:
      - match: {{field: asset_class}}
    limit_ref: aggregate_non_ig
""",
    )
    with pytest.raises(ConfigError) as exc_info:
        load_config(broken)
    assert "exactly one" in str(exc_info.value)


def test_field_match_with_two_predicates_rejected(tmp_path):
    broken = _write(
        tmp_path,
        "broken_match2.yaml",
        f"""
label: "Broken Firm"
{_VALID_PRESENTATION}
figures:
  aggregate_non_ig:
    kind: aggregate
    include:
      - match: {{field: asset_class, equals: "High Yield Bonds", in: ["High Yield Bonds"]}}
    limit_ref: aggregate_non_ig
""",
    )
    with pytest.raises(ConfigError) as exc_info:
        load_config(broken)
    assert "exactly one" in str(exc_info.value)


def test_unknown_top_level_field_rejected(tmp_path):
    broken = _write(
        tmp_path,
        "broken_extra.yaml",
        f"""
label: "Broken Firm"
{_VALID_PRESENTATION}
figures: {{}}
unexpected_field: 123
""",
    )
    with pytest.raises(ConfigError) as exc_info:
        load_config(broken)
    assert "unexpected_field" in str(exc_info.value)


def test_missing_required_field_rejected(tmp_path):
    broken = _write(
        tmp_path,
        "broken_missing.yaml",
        """
label: "Broken Firm"
presentation:
  utilization: {format: percent, decimals: 1, rounding: ROUND_HALF_UP}
  percentage: {decimals: 1, rounding: ROUND_HALF_UP}
  duration: {decimals: 2, rounding: ROUND_HALF_UP}
  # currency is missing
figures: {}
""",
    )
    with pytest.raises(ConfigError) as exc_info:
        load_config(broken)
    assert "currency" in str(exc_info.value)
