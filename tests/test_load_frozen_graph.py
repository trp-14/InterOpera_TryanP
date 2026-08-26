from pathlib import Path

import pytest

from src.compute.figures import compute_all_figures
from src.compute.formatters import render_all
from src.config.loader import load_config
from src.graph.builder import build_graph, freeze_graph, load_frozen_graph

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def frozen_path(tmp_path_factory) -> Path:
    graph = build_graph(ROOT / "sample_docs" / "sample_fund_guidelines.pdf", ROOT / "sample_docs" / "sample_holdings.csv")
    path = tmp_path_factory.mktemp("frozen") / "graph.json"
    freeze_graph(graph, path)
    return path


def test_round_trip_preserves_content_hash(frozen_path, tmp_path):
    loaded = load_frozen_graph(frozen_path)
    re_frozen_path = tmp_path / "re_frozen.json"
    original_hash = freeze_graph(build_graph(ROOT / "sample_docs" / "sample_fund_guidelines.pdf", ROOT / "sample_docs" / "sample_holdings.csv"), tmp_path / "original.json")
    re_frozen_hash = freeze_graph(loaded, re_frozen_path)
    assert original_hash == re_frozen_hash


def test_loaded_graph_produces_identical_figures(frozen_path):
    fresh_graph = build_graph(ROOT / "sample_docs" / "sample_fund_guidelines.pdf", ROOT / "sample_docs" / "sample_holdings.csv")
    loaded_graph = load_frozen_graph(frozen_path)
    config = load_config(ROOT / "config" / "firm_a.yaml")

    fresh_results = render_all(compute_all_figures(fresh_graph, config), config)
    loaded_results = render_all(compute_all_figures(loaded_graph, config), config)
    assert fresh_results == loaded_results


def test_tampered_graph_json_is_rejected(frozen_path, tmp_path):
    import json

    data = json.loads(frozen_path.read_text(encoding="utf-8"))
    data["nodes"][0]["extraction_confidence"] = 0.01  # tamper with a value, leave content_hash stale
    tampered_path = tmp_path / "tampered.json"
    tampered_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="content_hash mismatch"):
        load_frozen_graph(tampered_path)
