"""Compute all 13 compliance figures from the graph, config-driven (BUILD_PLAN.md Step 5).

Every figure here:
1. traverses the graph to find the relevant nodes (never reads the CSV —
   CLAUDE.md section 3.4),
2. computes with Decimal only (never float/round() — section 3.3),
3. resolves its limit by traversing to the real Limit/Threshold node,
4. returns a graph_path built from the recorded traversal (traversal.py),
   never a hand-written string.

Firm differences live entirely in `config` (an already-validated FirmConfig)
— nothing here branches on a firm name (section 3.1). Zero imports from
src.narrative or an LLM SDK (section 3.2) — there's a test that greps this.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

import networkx as nx

from src.compute import aggregations
from src.config.models import AggregateFigureConfig, ConcentrationFigureConfig, FieldMatch, FirmConfig
from src.graph import schema, traversal
from src.graph.traversal import TraversalResult


@dataclass(frozen=True)
class Citation:
    source_doc: str
    page: int
    chunk_id: str
    passage_summary: str


@dataclass(frozen=True)
class FigureResult:
    figure: str
    status: str  # "OK" | "BREACH" | "AT_LIMIT" | "ERROR"
    unit: str  # "percent" | "years" | "sgd_per_bp" | ""
    value: Decimal | None
    limit_min: Decimal | None
    limit_max: Decimal | None
    limit_display_mode: str  # "range" | "min_only" | "max_only" | "none"
    utilization: Decimal | None  # raw ratio on a 0-100 percent scale, or None
    graph_path: str
    citation: Citation | None
    error: str | None = None
    value_str: str | None = None
    utilization_str: str | None = None

    def with_display(self, value_str: str, utilization_str: str) -> "FigureResult":
        return replace(self, value_str=value_str, utilization_str=utilization_str)


# --- shared helpers ------------------------------------------------------------

_INVESTMENT_GRADE_RATINGS = frozenset(
    {"AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-"}
)


def _is_below_investment_grade(credit_rating: object) -> bool:
    if not credit_rating:
        return False
    return credit_rating not in _INVESTMENT_GRADE_RATINGS


def _match_predicate(match: FieldMatch, record: dict) -> bool:
    field_value = record.get(match.field)
    if match.equals is not None:
        return field_value == match.equals
    if match.in_values is not None:
        return field_value in match.in_values
    if match.below_investment_grade is not None:
        return match.below_investment_grade == _is_below_investment_grade(field_value)
    raise ValueError(f"FieldMatch for field={match.field!r} has no predicate set")


def _position_record(graph: nx.MultiDiGraph, position_id: str) -> dict:
    data = graph.nodes[position_id]
    asset_class_id = traversal.out_neighbors(graph, position_id, schema.BELONGS_TO)[0]
    issuer_id = traversal.out_neighbors(graph, position_id, schema.ISSUED_BY)[0]
    issuer_data = graph.nodes[issuer_id]

    parent_ids = traversal.in_neighbors(graph, issuer_id, schema.PARENT_OF)
    parent_issuer_name = graph.nodes[parent_ids[0]]["name"] if parent_ids else issuer_data["name"]

    return {
        "position_id": position_id,
        "asset_class_id": asset_class_id,
        "asset_class": graph.nodes[asset_class_id]["name"],
        "market_value_sgd": data["market_value_sgd"],
        "modified_duration": data["modified_duration"],
        "credit_rating": data["credit_rating"],
        "downgraded_from": data["downgraded_from"],
        "issuer_id": issuer_id,
        "issuer_name": issuer_data["name"],
        "issuer_type": issuer_data["issuer_type"],
        "parent_issuer": parent_issuer_name,
    }


def _all_position_records(graph: nx.MultiDiGraph) -> list[dict]:
    position_ids = sorted(n for n, d in graph.nodes(data=True) if d.get("node_type") == schema.POSITION)
    return [_position_record(graph, pid) for pid in position_ids]


def _nav(graph: nx.MultiDiGraph) -> Decimal:
    return sum((r["market_value_sgd"] for r in _all_position_records(graph)), Decimal(0))


def _status(value: Decimal, limit_min: Decimal | None, limit_max: Decimal | None) -> str:
    if limit_min is not None and value < limit_min:
        return "BREACH"
    if limit_max is not None and value > limit_max:
        return "BREACH"
    if limit_max is not None and value == limit_max:
        return "AT_LIMIT"
    if limit_min is not None and value == limit_min:
        return "AT_LIMIT"
    return "OK"


def _utilization(value: Decimal, limit_min: Decimal | None, limit_max: Decimal | None, denominator: str) -> Decimal | None:
    if denominator == "max" and limit_max:
        return (value / limit_max) * 100
    if denominator == "min" and limit_min:
        return (value / limit_min) * 100
    return None


def _citation_from_chunk(graph: nx.MultiDiGraph, chunk_id: str, passage_summary: str) -> Citation:
    chunk_data = graph.nodes[chunk_id]
    return Citation(
        source_doc=chunk_data["source_doc"],
        page=chunk_data["page"],
        chunk_id=chunk_id,
        passage_summary=passage_summary,
    )


def _node_path(nodes: list[str]) -> TraversalResult:
    """A zero-hop 'traversal' — used when we resolve a node directly (no
    edge to walk), e.g. the standalone concentration Limit nodes. Still goes
    through the same rendering machinery as every other graph_path, instead
    of being a hand-written string."""
    return TraversalResult(nodes=nodes, hops=[])


# --- kind: simple allocation (7 figures) ----------------------------------------

def _compute_allocation_figure(
    graph: nx.MultiDiGraph, figure_name: str, asset_slug: str, *, limit_display_mode: str, utilization_denominator: str
) -> FigureResult:
    asset_id = traversal.find_node(graph, schema.ASSET_CLASS, display_id=asset_slug)
    limit_path = traversal.follow(graph, asset_id, schema.HAS_LIMIT)
    limit_data = graph.nodes[limit_path.nodes[-1]]

    nav = _nav(graph)
    position_ids = traversal.in_neighbors(graph, asset_id, schema.BELONGS_TO)
    total = sum((graph.nodes[pid]["market_value_sgd"] for pid in position_ids), Decimal(0))
    value = (total / nav) * 100

    status = _status(value, limit_data["min_value"], limit_data["max_value"])
    utilization = _utilization(value, limit_data["min_value"], limit_data["max_value"], utilization_denominator)
    citation = _citation_from_chunk(graph, limit_data["chunk_id"], f"guidelines allocation table: {limit_data['name']}")

    return FigureResult(
        figure=figure_name, status=status, unit="percent", value=value,
        limit_min=limit_data["min_value"], limit_max=limit_data["max_value"],
        limit_display_mode=limit_display_mode, utilization=utilization,
        graph_path=limit_path.as_path_string(graph), citation=citation,
    )


def compute_sgs_allocation(graph: nx.MultiDiGraph) -> FigureResult:
    return _compute_allocation_figure(graph, "sgs_allocation", "sgs", limit_display_mode="range", utilization_denominator="max")


def compute_mas_bills_allocation(graph: nx.MultiDiGraph) -> FigureResult:
    return _compute_allocation_figure(graph, "mas_bills_allocation", "mas_bills", limit_display_mode="range", utilization_denominator="max")


def compute_ig_corporate_allocation(graph: nx.MultiDiGraph) -> FigureResult:
    return _compute_allocation_figure(graph, "ig_corporate_allocation", "ig_corporate", limit_display_mode="range", utilization_denominator="max")


def compute_high_yield_allocation(graph: nx.MultiDiGraph) -> FigureResult:
    return _compute_allocation_figure(graph, "high_yield_allocation", "high_yield", limit_display_mode="range", utilization_denominator="max")


def compute_fx_bonds_allocation(graph: nx.MultiDiGraph) -> FigureResult:
    return _compute_allocation_figure(graph, "fx_bonds_allocation", "fx_bonds", limit_display_mode="range", utilization_denominator="max")


def compute_structured_credit_allocation(graph: nx.MultiDiGraph) -> FigureResult:
    return _compute_allocation_figure(graph, "structured_credit_allocation", "structured_credit", limit_display_mode="range", utilization_denominator="max")


def compute_cash_allocation(graph: nx.MultiDiGraph) -> FigureResult:
    # Cash's guideline row has both a min (5%) and max (25%), but the
    # regulatory concern here is the liquidity *floor* — unlike every other
    # allocation limit, nobody polices an upper bound on cash. Status still
    # checks the true min+max from the Limit node; only the display/
    # utilization treat it as min-only (matches CLAUDE.md section 7 ground truth).
    return _compute_allocation_figure(graph, "cash_allocation", "cash", limit_display_mode="min_only", utilization_denominator="none")


# --- kind: aggregate (2 figures) ------------------------------------------------

def _build_membership_path(graph: nx.MultiDiGraph, aggregate_id: str, records: list[dict]) -> str:
    segments: list[str] = []
    asset_class_ids_via_edge = set(traversal.in_neighbors(graph, aggregate_id, schema.CONTRIBUTES_TO))
    seen_asset_classes: set[str] = set()
    seen_positions: set[str] = set()

    for record in records:
        asset_class_id = record["asset_class_id"]
        if asset_class_id in asset_class_ids_via_edge:
            if asset_class_id not in seen_asset_classes:
                seen_asset_classes.add(asset_class_id)
                segments.append(traversal.follow(graph, asset_class_id, schema.CONTRIBUTES_TO).as_path_string(graph))
        else:
            position_id = record["position_id"]
            if position_id not in seen_positions:
                seen_positions.add(position_id)
                segments.append(traversal.follow(graph, position_id, schema.BELONGS_TO).as_path_string(graph))

    segments.append(traversal.follow(graph, aggregate_id, schema.HAS_LIMIT).as_path_string(graph))
    return " ; ".join(segments)


def _compute_aggregate_figure(graph: nx.MultiDiGraph, config: FirmConfig, figure_name: str, aggregate_slug: str) -> FigureResult:
    figure_config = config.figures[figure_name]
    if not isinstance(figure_config, AggregateFigureConfig):
        raise TypeError(f"{figure_name} is not configured as an aggregate figure")

    records = aggregations.filter_by(
        _all_position_records(graph),
        lambda r: any(_match_predicate(rule.match, r) for rule in figure_config.include),
    )

    aggregate_id = traversal.find_node(graph, schema.AGGREGATE, display_id=aggregate_slug)
    limit_id = traversal.follow(graph, aggregate_id, schema.HAS_LIMIT).nodes[-1]
    limit_data = graph.nodes[limit_id]

    nav = _nav(graph)
    total = sum((r["market_value_sgd"] for r in records), Decimal(0))
    value = (total / nav) * 100

    status = _status(value, limit_data["min_value"], limit_data["max_value"])
    denominator = "min" if limit_data["max_value"] is None else "max"
    utilization = _utilization(value, limit_data["min_value"], limit_data["max_value"], denominator)
    limit_display_mode = "min_only" if limit_data["max_value"] is None else "max_only"

    citation = _citation_from_chunk(graph, limit_data["chunk_id"], f"guidelines: {limit_data['name']}")

    return FigureResult(
        figure=figure_name, status=status, unit="percent", value=value,
        limit_min=limit_data["min_value"], limit_max=limit_data["max_value"],
        limit_display_mode=limit_display_mode, utilization=utilization,
        graph_path=_build_membership_path(graph, aggregate_id, records), citation=citation,
    )


def compute_aggregate_non_ig(graph: nx.MultiDiGraph, config: FirmConfig) -> FigureResult:
    return _compute_aggregate_figure(graph, config, "aggregate_non_ig", "non_ig")


def compute_liquidity_ratio(graph: nx.MultiDiGraph, config: FirmConfig) -> FigureResult:
    return _compute_aggregate_figure(graph, config, "liquidity_ratio", "liquid_assets")


# --- kind: concentration (2 figures) --------------------------------------------

def _build_concentration_path(graph: nx.MultiDiGraph, winning_records: list[dict], group_by_field: str, limit_id: str) -> str:
    segments: list[str] = []
    seen_issuers: set[str] = set()

    for record in winning_records:
        issuer_id = record["issuer_id"]
        if issuer_id in seen_issuers:
            continue
        seen_issuers.add(issuer_id)
        segments.append(traversal.follow(graph, record["position_id"], schema.ISSUED_BY).as_path_string(graph))

        if group_by_field == "parent_issuer":
            parent_ids = traversal.in_neighbors(graph, issuer_id, schema.PARENT_OF)
            if parent_ids:
                segments.append(traversal.follow(graph, parent_ids[0], schema.PARENT_OF).as_path_string(graph))

    segments.append(_node_path([limit_id]).as_path_string(graph))
    return " ; ".join(segments)


def _compute_concentration_figure(graph: nx.MultiDiGraph, config: FirmConfig, figure_name: str) -> FigureResult:
    figure_config = config.figures[figure_name]
    if not isinstance(figure_config, ConcentrationFigureConfig):
        raise TypeError(f"{figure_name} is not configured as a concentration figure")

    records = aggregations.filter_by(_all_position_records(graph), lambda r: _match_predicate(figure_config.filter, r))
    groups = aggregations.sum_by(records, figure_config.group_by, "market_value_sgd")
    if not groups:
        raise ValueError(f"no positions matched the filter for {figure_name}")

    winning_key = max(groups, key=lambda k: groups[k])
    winning_records = [r for r in records if r[figure_config.group_by] == winning_key]

    nav = _nav(graph)
    value = (groups[winning_key] / nav) * 100

    limit_id = f"limit:{figure_config.limit_ref}"
    limit_data = graph.nodes[limit_id]

    status = _status(value, limit_data["min_value"], limit_data["max_value"])
    utilization = _utilization(value, limit_data["min_value"], limit_data["max_value"], "max")
    citation = _citation_from_chunk(graph, limit_data["chunk_id"], f"guidelines: {limit_data['name']}")

    return FigureResult(
        figure=figure_name, status=status, unit="percent", value=value,
        limit_min=limit_data["min_value"], limit_max=limit_data["max_value"],
        limit_display_mode="max_only", utilization=utilization,
        graph_path=_build_concentration_path(graph, winning_records, figure_config.group_by, limit_id),
        citation=citation,
    )


def compute_single_issuer_concentration(graph: nx.MultiDiGraph, config: FirmConfig) -> FigureResult:
    return _compute_concentration_figure(graph, config, "single_issuer_concentration")


def compute_gre_concentration(graph: nx.MultiDiGraph, config: FirmConfig) -> FigureResult:
    return _compute_concentration_figure(graph, config, "gre_concentration")


# --- kind: risk metric (2 figures) ----------------------------------------------

def compute_portfolio_duration(graph: nx.MultiDiGraph) -> FigureResult:
    metric_id = traversal.find_node(graph, schema.RISK_METRIC, display_id="portfolio_duration")
    threshold_path = traversal.follow(graph, metric_id, schema.HAS_THRESHOLD)
    threshold_data = graph.nodes[threshold_path.nodes[-1]]

    value = aggregations.weighted_average(_all_position_records(graph), "modified_duration", "market_value_sgd")
    status = _status(value, threshold_data["min_value"], threshold_data["max_value"])
    citation = _citation_from_chunk(graph, threshold_data["chunk_id"], "guidelines section 3.1: modified duration limit")

    return FigureResult(
        figure="portfolio_duration", status=status, unit="years", value=value,
        limit_min=threshold_data["min_value"], limit_max=threshold_data["max_value"],
        limit_display_mode="range", utilization=None,
        graph_path=threshold_path.as_path_string(graph), citation=citation,
    )


def compute_portfolio_dv01(graph: nx.MultiDiGraph) -> FigureResult:
    metric_id = traversal.find_node(graph, schema.RISK_METRIC, display_id="portfolio_dv01")
    threshold_path = traversal.follow(graph, metric_id, schema.HAS_THRESHOLD)
    threshold_data = graph.nodes[threshold_path.nodes[-1]]

    nav = _nav(graph)
    # Deliberately recomputed from the unrounded weighted average, not the
    # (possibly-rounded) portfolio_duration figure's display value — CLAUDE.md
    # section 7: using the rounded 3.88 here gives 38,800 and fails reconciliation.
    unrounded_duration = aggregations.weighted_average(_all_position_records(graph), "modified_duration", "market_value_sgd")
    value = nav * unrounded_duration * Decimal("0.0001")

    status = _status(value, threshold_data["min_value"], threshold_data["max_value"])
    utilization = _utilization(value, threshold_data["min_value"], threshold_data["max_value"], "max")
    citation = _citation_from_chunk(graph, threshold_data["chunk_id"], "guidelines section 3.1: portfolio DV01 limit")

    return FigureResult(
        figure="portfolio_dv01", status=status, unit="sgd_per_bp", value=value,
        limit_min=threshold_data["min_value"], limit_max=threshold_data["max_value"],
        limit_display_mode="max_only", utilization=utilization,
        graph_path=threshold_path.as_path_string(graph), citation=citation,
    )


# --- orchestration ---------------------------------------------------------------

FIGURE_ORDER = (
    "sgs_allocation",
    "mas_bills_allocation",
    "ig_corporate_allocation",
    "high_yield_allocation",
    "fx_bonds_allocation",
    "structured_credit_allocation",
    "cash_allocation",
    "aggregate_non_ig",
    "single_issuer_concentration",
    "gre_concentration",
    "liquidity_ratio",
    "portfolio_duration",
    "portfolio_dv01",
)


def compute_all_figures(graph: nx.MultiDiGraph, config: FirmConfig) -> list[FigureResult]:
    builders = {
        "sgs_allocation": lambda: compute_sgs_allocation(graph),
        "mas_bills_allocation": lambda: compute_mas_bills_allocation(graph),
        "ig_corporate_allocation": lambda: compute_ig_corporate_allocation(graph),
        "high_yield_allocation": lambda: compute_high_yield_allocation(graph),
        "fx_bonds_allocation": lambda: compute_fx_bonds_allocation(graph),
        "structured_credit_allocation": lambda: compute_structured_credit_allocation(graph),
        "cash_allocation": lambda: compute_cash_allocation(graph),
        "aggregate_non_ig": lambda: compute_aggregate_non_ig(graph, config),
        "single_issuer_concentration": lambda: compute_single_issuer_concentration(graph, config),
        "gre_concentration": lambda: compute_gre_concentration(graph, config),
        "liquidity_ratio": lambda: compute_liquidity_ratio(graph, config),
        "portfolio_duration": lambda: compute_portfolio_duration(graph),
        "portfolio_dv01": lambda: compute_portfolio_dv01(graph),
    }

    results = []
    for name in FIGURE_ORDER:
        try:
            results.append(builders[name]())
        except Exception as exc:  # noqa: BLE001 - deliberately broad: any failure becomes an ERROR figure, never a crash
            results.append(
                FigureResult(
                    figure=name, status="ERROR", unit="", value=None,
                    limit_min=None, limit_max=None, limit_display_mode="none",
                    utilization=None, graph_path="", citation=None, error=str(exc),
                )
            )
    return results
