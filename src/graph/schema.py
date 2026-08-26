"""Graph node and edge type constants (CLAUDE.md section 5 / BUILD_PLAN.md Step 3).

networkx doesn't enforce a schema on its own — this module is the single
source of truth for which node_type / edge_type strings are valid, so
builder.py and traversal.py reference these constants instead of repeating
string literals.

Every node in the graph carries these provenance fields (some are None for
data with no page/chunk concept, e.g. CSV-derived nodes):
    source_doc, page, chunk_id, ingested_at, extraction_confidence
"""
from __future__ import annotations

# --- Node types --------------------------------------------------------------
DOCUMENT = "Document"
CHUNK = "Chunk"
ASSET_CLASS = "AssetClass"
LIMIT = "Limit"
RISK_METRIC = "RiskMetric"
THRESHOLD = "Threshold"
BREACH_ACTION = "BreachAction"
OWNER = "Owner"
ISSUER = "Issuer"
POSITION = "Position"
AGGREGATE = "Aggregate"

NODE_TYPES = frozenset(
    {
        DOCUMENT,
        CHUNK,
        ASSET_CLASS,
        LIMIT,
        RISK_METRIC,
        THRESHOLD,
        BREACH_ACTION,
        OWNER,
        ISSUER,
        POSITION,
        AGGREGATE,
    }
)

# --- Edge types ----------------------------------------------------------------
HAS_LIMIT = "HAS_LIMIT"
HAS_THRESHOLD = "HAS_THRESHOLD"
ON_BREACH = "ON_BREACH"
NOTIFIES = "NOTIFIES"
ISSUED_BY = "ISSUED_BY"
PARENT_OF = "PARENT_OF"
BELONGS_TO = "BELONGS_TO"
CONTRIBUTES_TO = "CONTRIBUTES_TO"
SOURCED_FROM = "SOURCED_FROM"

EDGE_TYPES = frozenset(
    {
        HAS_LIMIT,
        HAS_THRESHOLD,
        ON_BREACH,
        NOTIFIES,
        ISSUED_BY,
        PARENT_OF,
        BELONGS_TO,
        CONTRIBUTES_TO,
        SOURCED_FROM,
    }
)

PROVENANCE_FIELDS = ("source_doc", "page", "chunk_id", "ingested_at", "extraction_confidence")

HUMAN_REVIEW_CONFIDENCE_THRESHOLD = 0.9
