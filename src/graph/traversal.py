"""Graph traversal helpers that record the path walked (BUILD_PLAN.md Step 3).

Every helper here returns the sequence of nodes/edges it actually visited,
not just the end result — this is what lets Step 5 build a real `graph_path`
string for each figure's citation, instead of hand-writing one
(CLAUDE.md constraint 2: every figure must trace `figure -> graph_path ->
source chunk`).
"""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx


@dataclass(frozen=True)
class Hop:
    from_node: str
    edge_type: str
    to_node: str


@dataclass(frozen=True)
class TraversalResult:
    nodes: list[str]  # node ids visited in order, including the start node
    hops: list[Hop]

    def as_path_string(self, graph: nx.MultiDiGraph) -> str:
        """Render e.g. '(AssetClass:high_yield)-[:CONTRIBUTES_TO]->(Aggregate:non_ig)'."""
        if not self.nodes:
            return ""
        parts = [_render_node(graph, self.nodes[0])]
        for hop in self.hops:
            parts.append(f"-[:{hop.edge_type}]->{_render_node(graph, hop.to_node)}")
        return "".join(parts)


def _render_node(graph: nx.MultiDiGraph, node_id: str) -> str:
    data = graph.nodes[node_id]
    node_type = data.get("node_type", "?")
    display_id = data.get("display_id", node_id)
    return f"({node_type}:{display_id})"


def find_node(graph: nx.MultiDiGraph, node_type: str, **attrs: object) -> str:
    """Find the single node of `node_type` whose attributes match `attrs`.

    Raises if zero or more than one node matches — callers should never
    silently pick "the first" match for something as load-bearing as a
    figure's source data.
    """
    matches = [
        node_id
        for node_id, data in graph.nodes(data=True)
        if data.get("node_type") == node_type and all(data.get(k) == v for k, v in attrs.items())
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly 1 {node_type} node matching {attrs}, found {len(matches)}: {matches}")
    return matches[0]


def follow(graph: nx.MultiDiGraph, start: str, *edge_types: str) -> TraversalResult:
    """Walk a chain of single-hop edge types starting at `start`.

    At each step, follows the first outgoing edge of the given type. Raises
    if no such edge exists, rather than silently stopping short.
    """
    nodes = [start]
    hops: list[Hop] = []
    current = start

    for edge_type in edge_types:
        next_node = None
        for _, target, data in graph.out_edges(current, data=True):
            if data.get("edge_type") == edge_type:
                next_node = target
                break
        if next_node is None:
            raise ValueError(f"no outgoing {edge_type!r} edge found from {current!r}")
        hops.append(Hop(from_node=current, edge_type=edge_type, to_node=next_node))
        nodes.append(next_node)
        current = next_node

    return TraversalResult(nodes=nodes, hops=hops)


def out_neighbors(graph: nx.MultiDiGraph, node_id: str, edge_type: str) -> list[str]:
    """All targets reachable from `node_id` via one hop of `edge_type` (order preserved)."""
    return [target for _, target, data in graph.out_edges(node_id, data=True) if data.get("edge_type") == edge_type]


def in_neighbors(graph: nx.MultiDiGraph, node_id: str, edge_type: str) -> list[str]:
    """All sources that reach `node_id` via one hop of `edge_type` (order preserved)."""
    return [source for source, _, data in graph.in_edges(node_id, data=True) if data.get("edge_type") == edge_type]
