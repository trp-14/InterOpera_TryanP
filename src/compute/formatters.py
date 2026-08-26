"""Presentation-only formatting (BUILD_PLAN.md Step 5).

Nothing here computes a figure or decides a status — it only turns an
already-computed Decimal into a display string, using decimals/rounding
from config (CLAUDE.md section 7: "computation and presentation must be
separate", proven by Firm B re-rendering every utilization in bps from the
exact same underlying ratios).

Limit bounds (min/max) are rendered verbatim, at the source document's own
precision — they're policy constants already, not something to round.
Only *computed* values (value, utilization) go through explicit
decimals+rounding from config.
"""
from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from src.compute.figures import FigureResult
from src.config.models import FirmConfig, NumberPresentation, UtilizationPresentation

_ROUNDING = {"ROUND_HALF_UP": ROUND_HALF_UP, "ROUND_DOWN": ROUND_DOWN}


def _quantize(value: Decimal, decimals: int, rounding: str) -> Decimal:
    exponent = Decimal(1).scaleb(-decimals)
    return value.quantize(exponent, rounding=_ROUNDING[rounding])


def format_percent(value: Decimal, presentation: NumberPresentation) -> str:
    return f"{_quantize(value, presentation.decimals, presentation.rounding)}%"


def format_duration(value: Decimal, presentation: NumberPresentation) -> str:
    return f"{_quantize(value, presentation.decimals, presentation.rounding)} yrs"


def format_currency(value: Decimal, presentation: NumberPresentation) -> str:
    return f"SGD {_quantize(value, presentation.decimals, presentation.rounding):,}"


def format_utilization(ratio_percent: Decimal | None, presentation: UtilizationPresentation) -> str:
    """`ratio_percent` is value/limit already expressed on a 0-100 percent scale."""
    if ratio_percent is None:
        return "n/a"
    if presentation.format == "percent":
        return f"{_quantize(ratio_percent, presentation.decimals, presentation.rounding)}%"
    # basis_points: (ratio_percent / 100) is the raw fraction; * 10000 for bps == ratio_percent * 100
    bps = ratio_percent * 100
    return f"{_quantize(bps, presentation.decimals, presentation.rounding)} bps"


def format_limit_string(result: FigureResult) -> str:
    if result.status == "ERROR":
        return "n/a"
    if result.limit_display_mode == "range":
        # en-dash, matching the provided answer key workbook exactly (e.g.
        # "20–60%") - Step 9 reconciliation diffs this string verbatim.
        suffix = " yrs" if result.unit == "years" else "%"
        return f"{result.limit_min}–{result.limit_max}{suffix}"
    if result.limit_display_mode == "min_only":
        return f"min {result.limit_min}%"
    if result.limit_display_mode == "max_only":
        if result.unit == "sgd_per_bp":
            return f"max {result.limit_max:,}"
        return f"max {result.limit_max}%"
    return "n/a"


def to_report_dict(result: FigureResult) -> dict:
    """Assemble the final per-figure JSON shape (BUILD_PLAN.md Step 5 output shape)."""
    if result.status == "ERROR":
        return {"figure": result.figure, "status": "ERROR", "error": result.error}

    return {
        "figure": result.figure,
        "value": result.value_str,
        "status": result.status.replace("_", " "),
        "limit": format_limit_string(result),
        "utilization": result.utilization_str,
        "graph_path": result.graph_path,
        "rule": result.rule_summary,
        "citation": (
            {
                "source_doc": result.citation.source_doc,
                "page": result.citation.page,
                "chunk_id": result.citation.chunk_id,
                "passage_summary": result.citation.passage_summary,
            }
            if result.citation is not None
            else None
        ),
    }


def render_all(results: list[FigureResult], config: FirmConfig) -> list[dict]:
    """Attach presentation strings (value/utilization) per config, then build report dicts.

    Figures carry only raw Decimal values until this point — this is the
    single place formatting actually happens.
    """
    rendered = []
    for result in results:
        if result.status == "ERROR":
            rendered.append(result)
            continue

        if result.unit == "percent":
            value_str = format_percent(result.value, config.presentation.percentage)
        elif result.unit == "years":
            value_str = format_duration(result.value, config.presentation.duration)
        elif result.unit == "sgd_per_bp":
            value_str = format_currency(result.value, config.presentation.currency) + " / bp"
        else:
            raise ValueError(f"unknown unit {result.unit!r} for figure {result.figure!r}")

        utilization_str = format_utilization(result.utilization, config.presentation.utilization)
        rendered.append(result.with_display(value_str, utilization_str))

    return [to_report_dict(r) for r in rendered]
