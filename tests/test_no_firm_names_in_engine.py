"""Guard CLAUDE.md section 3.1: no firm identifier under src/compute,
src/graph, or src/ingestion (BUILD_PLAN.md Step 10).

`firm_a` / `firm_b` (any case) are unambiguous and always forbidden. Bare
"A" / "B" are trickier: S&P credit-rating grades legitimately include bare
"A" and "B" (figures.py's investment-grade ratings set has "A" sitting
between "A+" and "A-"), so a literal grep for '"A"|"B"' — as CLAUDE.md's own
checklist command reads — flags that data as a false positive. This test
instead walks the AST and exempts a bare "A"/"B" only when it's one element
of a larger, clearly rating-scale-shaped literal collection (>=3 string
elements, all matching a rating-grade pattern, at least one multi-character
like "AAA"/"BBB-") — anywhere else, it's flagged same as CLAUDE.md intends.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARDED_DIRS = (ROOT / "src" / "compute", ROOT / "src" / "graph", ROOT / "src" / "ingestion")

_FIRM_TOKEN = re.compile(r"firm_a|firm_b", re.IGNORECASE)
_RATING_LIKE = re.compile(r"^[A-D]{1,3}[+-]?$")


def _all_python_files() -> list[Path]:
    files: list[Path] = []
    for directory in GUARDED_DIRS:
        files.extend(sorted(directory.rglob("*.py")))
    return files


def _ratings_like_element_ids(tree: ast.AST) -> set[int]:
    """id() of every string-literal AST node that sits inside a collection
    that looks like a full credit-rating scale, not a firm A/B pair."""
    exempt_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
            elts = node.elts
        elif isinstance(node, ast.Dict):
            elts = node.keys
        else:
            continue

        str_constants = [e for e in elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if len(str_constants) < 3:
            continue
        if not all(_RATING_LIKE.match(e.value) for e in str_constants):
            continue
        if not any(len(e.value) >= 2 for e in str_constants):
            continue
        exempt_ids.update(id(e) for e in str_constants)
    return exempt_ids


@pytest.mark.parametrize("path", _all_python_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_firm_names_in_engine(path: Path):
    source = path.read_text(encoding="utf-8")

    firm_tokens = _FIRM_TOKEN.findall(source)
    assert not firm_tokens, f"{path.relative_to(ROOT)} contains a firm_a/firm_b identifier"

    tree = ast.parse(source, filename=str(path))
    exempt_ids = _ratings_like_element_ids(tree)

    offending = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value in ("A", "B")
        and id(node) not in exempt_ids
    ]
    assert not offending, f"{path.relative_to(ROOT)} contains a bare 'A'/'B' string literal outside a credit-rating collection"


def test_the_exemption_does_not_swallow_a_bare_firm_pair():
    """The ratings-collection exemption must not accidentally whitelist a
    plain {"A", "B"} firm-choice set - only real multi-grade rating scales."""
    tree = ast.parse('x = {"A", "B"}')
    assert _ratings_like_element_ids(tree) == set()


def test_the_exemption_does_accept_a_real_ratings_scale():
    tree = ast.parse('x = {"AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-"}')
    assert len(_ratings_like_element_ids(tree)) == 10
