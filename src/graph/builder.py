"""Build the compliance graph from ingestion output and freeze it (BUILD_PLAN.md Step 3).

Everything the compute layer will ever read (CLAUDE.md constraint 3.4: figures
come from the graph, not the CSV) is assembled here from already-parsed
ingestion output — this module does no PDF/CSV reading of its own.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import networkx as nx

from src.graph import schema
from src.ingestion.chunker import chunk_pdf
from src.ingestion.csv_loader import load_holdings
from src.ingestion.pdf_parser import ExtractedLimit, parse_guidelines

# Maps each CSV `asset_class` string to the ExtractedLimit.name that governs
# it. Both sides of this mapping are fixed structure of the guidelines
# document and the holdings dataset, shared by every firm (not a firm-specific
# rule), so it belongs in the engine rather than in config/*.yaml.
ASSET_CLASS_TO_LIMIT_NAME = {
    "Singapore Government Securities": "sgs_allocation",
    "MAS Bills": "mas_bills_allocation",
    "Investment Grade Corporate Bonds": "ig_corporate_allocation",
    "High Yield Bonds": "high_yield_allocation",
    "Foreign Currency Bonds": "fx_bonds_allocation",
    "Structured Credit": "structured_credit_allocation",
    "Cash & Cash Equivalents": "cash_allocation",
}

NON_IG_ASSET_CLASSES = {"High Yield Bonds", "Structured Credit"}
LIQUID_ASSET_CLASSES = {"Singapore Government Securities", "MAS Bills", "Cash & Cash Equivalents"}

RISK_METRICS = (
    ("portfolio_duration", "Modified Duration"),
    ("portfolio_dv01", "Portfolio DV01"),
)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _asset_slug(limit_name: str) -> str:
    return limit_name.removesuffix("_allocation")


def _prov(source_doc: str, page: int | None, chunk_id: str | None, ingested_at: str, confidence: float) -> dict:
    return {
        "source_doc": source_doc,
        "page": page,
        "chunk_id": chunk_id,
        "ingested_at": ingested_at,
        "extraction_confidence": confidence,
    }


def _resolve_owner(breach_action_text: str) -> tuple[str | None, float]:
    """Derive who gets notified from a verbatim breach action string.

    This only needs to handle the exact phrasings this document uses — it's
    not a general NLP heuristic. An unrecognised phrasing falls back to
    `None` at reduced confidence, which routes the node into the human
    review gate instead of guessing at an owner.
    """
    if breach_action_text.startswith("PM "):
        return "PM", 1.0
    if breach_action_text.startswith("Risk Committee "):
        return "Risk Committee", 1.0
    return None, 0.5


def build_graph(pdf_path: str | Path, csv_path: str | Path) -> nx.MultiDiGraph:
    ingested_at = datetime.now(timezone.utc).isoformat()
    pdf_name = Path(pdf_path).name
    csv_name = Path(csv_path).name

    parsed = parse_guidelines(pdf_path)
    chunks = chunk_pdf(pdf_path)
    holdings = load_holdings(csv_path)

    limits_by_name: dict[str, ExtractedLimit] = {limit.name: limit for limit in parsed.limits}
    breach_by_metric = {b.risk_metric_name: b for b in parsed.breach_actions}

    graph = nx.MultiDiGraph()

    # --- Document + Chunk nodes ---------------------------------------------
    graph.add_node(
        f"doc:{pdf_name}",
        node_type=schema.DOCUMENT,
        display_id=pdf_name,
        name=pdf_name,
        **_prov(pdf_name, None, None, ingested_at, 1.0),
    )
    graph.add_node(
        f"doc:{csv_name}",
        node_type=schema.DOCUMENT,
        display_id=csv_name,
        name=csv_name,
        **_prov(csv_name, None, None, ingested_at, 1.0),
    )

    for chunk in chunks:
        graph.add_node(
            chunk.chunk_id,
            node_type=schema.CHUNK,
            display_id=chunk.chunk_id,
            text=chunk.text,
            **_prov(pdf_name, chunk.page, chunk.chunk_id, ingested_at, 1.0),
        )
        graph.add_edge(chunk.chunk_id, f"doc:{pdf_name}", edge_type=schema.SOURCED_FROM)

    # --- AssetClass + allocation Limit nodes --------------------------------
    for asset_class_name, limit_name in ASSET_CLASS_TO_LIMIT_NAME.items():
        limit = limits_by_name[limit_name]
        asset_id = f"assetclass:{_asset_slug(limit_name)}"

        graph.add_node(
            asset_id,
            node_type=schema.ASSET_CLASS,
            display_id=_asset_slug(limit_name),
            name=asset_class_name,
            **_prov(pdf_name, limit.page, limit.chunk_id, ingested_at, 1.0),
        )
        graph.add_edge(asset_id, limit.chunk_id, edge_type=schema.SOURCED_FROM)

        _add_limit_node(graph, limit, pdf_name, ingested_at)
        graph.add_edge(asset_id, f"limit:{limit_name}", edge_type=schema.HAS_LIMIT)

    # --- Aggregate nodes (non-IG exposure, liquid assets) -------------------
    _add_aggregate(
        graph, "non_ig", "Aggregate non-investment-grade exposure",
        NON_IG_ASSET_CLASSES, limits_by_name["aggregate_non_ig"], pdf_name, ingested_at,
    )
    _add_aggregate(
        graph, "liquid_assets", "Liquid assets",
        LIQUID_ASSET_CLASSES, limits_by_name["liquidity_ratio"], pdf_name, ingested_at,
    )

    # --- Standalone concentration Limit nodes (portfolio-wide policy, not
    # owned by one AssetClass/Aggregate — the compute layer matches these
    # against whichever issuer breaches them) --------------------------------
    for limit_name in ("single_issuer_concentration", "gre_concentration"):
        _add_limit_node(graph, limits_by_name[limit_name], pdf_name, ingested_at)

    # --- RiskMetric -> Threshold -> BreachAction -> Owner chain --------------
    for metric_name, display_name in RISK_METRICS:
        limit = limits_by_name[metric_name]
        breach = breach_by_metric[metric_name]
        owner_name, owner_confidence = _resolve_owner(breach.text)

        metric_id = f"riskmetric:{metric_name}"
        threshold_id = f"threshold:{metric_name}"
        breach_id = f"breachaction:{metric_name}"
        owner_slug = _slugify(owner_name) if owner_name else f"unresolved_{metric_name}"
        owner_id = f"owner:{owner_slug}"

        graph.add_node(
            metric_id, node_type=schema.RISK_METRIC, display_id=metric_name, name=display_name,
            **_prov(pdf_name, limit.page, limit.chunk_id, ingested_at, 1.0),
        )
        graph.add_edge(metric_id, limit.chunk_id, edge_type=schema.SOURCED_FROM)

        graph.add_node(
            threshold_id, node_type=schema.THRESHOLD, display_id=metric_name,
            unit=limit.unit, min_value=limit.min_value, max_value=limit.max_value,
            **_prov(pdf_name, limit.page, limit.chunk_id, ingested_at, 1.0),
        )
        graph.add_edge(threshold_id, limit.chunk_id, edge_type=schema.SOURCED_FROM)
        graph.add_edge(metric_id, threshold_id, edge_type=schema.HAS_THRESHOLD)

        graph.add_node(
            breach_id, node_type=schema.BREACH_ACTION, display_id=metric_name, text=breach.text,
            **_prov(pdf_name, breach.page, breach.chunk_id, ingested_at, 1.0),
        )
        graph.add_edge(breach_id, breach.chunk_id, edge_type=schema.SOURCED_FROM)
        graph.add_edge(threshold_id, breach_id, edge_type=schema.ON_BREACH)

        graph.add_node(
            owner_id, node_type=schema.OWNER, display_id=owner_slug, name=owner_name,
            **_prov(pdf_name, breach.page, breach.chunk_id, ingested_at, owner_confidence),
        )
        graph.add_edge(owner_id, breach.chunk_id, edge_type=schema.SOURCED_FROM)
        graph.add_edge(breach_id, owner_id, edge_type=schema.NOTIFIES)

    # --- Position + Issuer nodes ---------------------------------------------
    known_issuer_ids: set[str] = set()

    def _ensure_issuer(name: str, issuer_type: str | None) -> str:
        issuer_id = f"issuer:{_slugify(name)}"
        if issuer_id not in known_issuer_ids:
            graph.add_node(
                issuer_id, node_type=schema.ISSUER, display_id=_slugify(name), name=name, issuer_type=issuer_type,
                **_prov(csv_name, None, None, ingested_at, 1.0),
            )
            graph.add_edge(issuer_id, f"doc:{csv_name}", edge_type=schema.SOURCED_FROM)
            known_issuer_ids.add(issuer_id)
        return issuer_id

    for holding in holdings:
        issuer_id = _ensure_issuer(holding.issuer_name, holding.issuer_type)
        if holding.parent_issuer:
            parent_id = _ensure_issuer(holding.parent_issuer, "parent")
            if not graph.has_edge(parent_id, issuer_id):
                graph.add_edge(parent_id, issuer_id, edge_type=schema.PARENT_OF)

        position_id = f"position:{holding.instrument_id}"
        asset_id = f"assetclass:{_asset_slug(ASSET_CLASS_TO_LIMIT_NAME[holding.asset_class])}"

        graph.add_node(
            position_id, node_type=schema.POSITION, display_id=holding.instrument_id,
            instrument_name=holding.instrument_name, market_value_sgd=holding.market_value_sgd,
            modified_duration=holding.modified_duration, credit_rating=holding.credit_rating,
            downgraded_from=holding.downgraded_from, source_line=holding.source_line,
            **_prov(csv_name, None, None, ingested_at, 1.0),
        )
        graph.add_edge(position_id, f"doc:{csv_name}", edge_type=schema.SOURCED_FROM)
        graph.add_edge(position_id, asset_id, edge_type=schema.BELONGS_TO)
        graph.add_edge(position_id, issuer_id, edge_type=schema.ISSUED_BY)

    return graph


def _add_limit_node(graph: nx.MultiDiGraph, limit: ExtractedLimit, pdf_name: str, ingested_at: str) -> None:
    limit_id = f"limit:{limit.name}"
    graph.add_node(
        limit_id, node_type=schema.LIMIT, display_id=limit.name, name=limit.name,
        unit=limit.unit, min_value=limit.min_value, max_value=limit.max_value, raw_text=limit.raw_text,
        **_prov(pdf_name, limit.page, limit.chunk_id, ingested_at, 1.0),
    )
    graph.add_edge(limit_id, limit.chunk_id, edge_type=schema.SOURCED_FROM)


def _add_aggregate(
    graph: nx.MultiDiGraph,
    slug: str,
    display_name: str,
    member_asset_classes: set[str],
    limit: ExtractedLimit,
    pdf_name: str,
    ingested_at: str,
) -> None:
    aggregate_id = f"aggregate:{slug}"
    graph.add_node(
        aggregate_id, node_type=schema.AGGREGATE, display_id=slug, name=display_name,
        **_prov(pdf_name, limit.page, limit.chunk_id, ingested_at, 1.0),
    )
    graph.add_edge(aggregate_id, limit.chunk_id, edge_type=schema.SOURCED_FROM)

    _add_limit_node(graph, limit, pdf_name, ingested_at)
    graph.add_edge(aggregate_id, f"limit:{limit.name}", edge_type=schema.HAS_LIMIT)

    for asset_class_name in member_asset_classes:
        asset_id = f"assetclass:{_asset_slug(ASSET_CLASS_TO_LIMIT_NAME[asset_class_name])}"
        graph.add_edge(asset_id, aggregate_id, edge_type=schema.CONTRIBUTES_TO)


def find_review_needed(graph: nx.MultiDiGraph) -> list[dict]:
    """Nodes below the confidence threshold — these need human review before
    the graph is trusted (CLAUDE.md section 9 human gate)."""
    review = []
    for node_id, data in graph.nodes(data=True):
        confidence = data.get("extraction_confidence")
        if confidence is not None and confidence < schema.HUMAN_REVIEW_CONFIDENCE_THRESHOLD:
            review.append({"node_id": node_id, **data})
    return review


def json_default(obj: object) -> str:
    """`json.dumps(..., default=...)` hook for Decimal values (reused by main.py)."""
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"not JSON serialisable: {obj!r}")


def freeze_graph(graph: nx.MultiDiGraph, output_path: str | Path) -> str:
    """Write the graph to JSON with sorted keys (byte-stable output) and
    return its content hash. `ingested_at` is excluded from the hash — it's
    wall-clock noise, not content — so re-ingesting identical source files
    produces the same hash even though the timestamp differs.
    """
    nodes = [
        {"id": node_id, **{k: v for k, v in sorted(data.items())}}
        for node_id, data in sorted(graph.nodes(data=True), key=lambda item: item[0])
    ]
    edges = [
        {"source": u, "target": v, "key": key, **{k: v2 for k, v2 in sorted(data.items())}}
        for u, v, key, data in sorted(graph.edges(keys=True, data=True), key=lambda item: (item[0], item[1], str(item[2])))
    ]

    def _without_ingested_at(items: list[dict]) -> list[dict]:
        return [{k: v for k, v in item.items() if k != "ingested_at"} for item in items]

    hashable_payload = {"nodes": _without_ingested_at(nodes), "edges": _without_ingested_at(edges)}
    hashable_json = json.dumps(hashable_payload, sort_keys=True, default=json_default, separators=(",", ":"))
    content_hash = hashlib.sha256(hashable_json.encode("utf-8")).hexdigest()

    output = {"content_hash": content_hash, "nodes": nodes, "edges": edges}
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True, default=json_default), encoding="utf-8")

    return content_hash


# Only these attribute keys ever hold a Decimal (set in build_graph above);
# everything else round-trips through JSON as plain str/int/float/None/bool
# without needing type recovery.
_DECIMAL_FIELDS = frozenset({"min_value", "max_value", "market_value_sgd", "modified_duration"})


def load_frozen_graph(path: str | Path) -> nx.MultiDiGraph:
    """Read back a graph written by `freeze_graph` (BUILD_PLAN.md Step 5-9:
    `run`/`evaluate`/`trace` read the frozen graph, never re-ingest).

    Verifies the stored content_hash still matches the file's own
    nodes/edges before trusting it — if artifacts/graph.json was hand-edited
    or corrupted since it was frozen, this raises rather than silently
    computing figures from tampered data.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    def _restore_decimals(items: list[dict]) -> list[dict]:
        restored = []
        for item in items:
            fixed = dict(item)
            for field in _DECIMAL_FIELDS:
                if field in fixed and fixed[field] is not None:
                    fixed[field] = Decimal(fixed[field])
            restored.append(fixed)
        return restored

    def _without_ingested_at(items: list[dict]) -> list[dict]:
        return [{k: v for k, v in item.items() if k != "ingested_at"} for item in items]

    hashable_payload = {
        "nodes": _without_ingested_at(data["nodes"]),
        "edges": _without_ingested_at(data["edges"]),
    }
    hashable_json = json.dumps(hashable_payload, sort_keys=True, separators=(",", ":"))
    recomputed_hash = hashlib.sha256(hashable_json.encode("utf-8")).hexdigest()
    if recomputed_hash != data["content_hash"]:
        raise ValueError(
            f"{path}: content_hash mismatch (stored={data['content_hash'][:16]}..., "
            f"recomputed={recomputed_hash[:16]}...) — the frozen graph may have been tampered with"
        )

    graph = nx.MultiDiGraph()
    for node in _restore_decimals(data["nodes"]):
        node_id = node["id"]
        graph.add_node(node_id, **{k: v for k, v in node.items() if k != "id"})

    for edge in _restore_decimals(data["edges"]):
        attrs = {k: v for k, v in edge.items() if k not in ("source", "target", "key")}
        graph.add_edge(edge["source"], edge["target"], key=edge["key"], **attrs)

    return graph


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    pdf_path = root / "sample_docs" / "sample_fund_guidelines.pdf"
    csv_path = root / "sample_docs" / "sample_holdings.csv"

    g = build_graph(pdf_path, csv_path)
    print(f"graph: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")

    review = find_review_needed(g)
    print(f"nodes needing human review (confidence < {schema.HUMAN_REVIEW_CONFIDENCE_THRESHOLD}): {len(review)}")
    for item in review:
        print(f"  {item['node_id']}: confidence={item['extraction_confidence']}")

    content_hash = freeze_graph(g, root / "artifacts" / "graph.json")
    print(f"froze graph to artifacts/graph.json, content_hash={content_hash}")

    # --- Step 3 verify: multi-hop query, by traversal only ------------------
    from src.graph import traversal

    print("\n=== verify: 'if portfolio duration exceeds its limit, what is the")
    print("    breach action and who is notified?' (traversal only) ===")
    start = traversal.find_node(g, schema.RISK_METRIC, display_id="portfolio_duration")
    result = traversal.follow(g, start, schema.HAS_THRESHOLD, schema.ON_BREACH, schema.NOTIFIES)
    owner_node = g.nodes[result.nodes[-1]]
    print(f"path walked: {result.as_path_string(g)}")
    print(f"answer: {owner_node['name']} - {g.nodes[result.nodes[-2]]['text']}")
