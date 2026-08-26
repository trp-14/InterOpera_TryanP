"""Guard CLAUDE.md section 3.2: src/compute and src/graph must never import
an LLM SDK, or anything under src/narrative (BUILD_PLAN.md Step 10).

Uses ast parsing rather than a text grep, so a docstring/comment that merely
*mentions* "anthropic" (several of these modules explain the rule in prose)
doesn't trip the test — only a real `import` statement does.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARDED_DIRS = (ROOT / "src" / "compute", ROOT / "src" / "graph")
FORBIDDEN_MODULES = ("anthropic", "openai", "httpx", "src.narrative")


def _imported_module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _all_python_files() -> list[Path]:
    files: list[Path] = []
    for directory in GUARDED_DIRS:
        files.extend(sorted(directory.rglob("*.py")))
    return files


@pytest.mark.parametrize("path", _all_python_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_forbidden_imports(path: Path):
    imported = _imported_module_names(path)
    for forbidden in FORBIDDEN_MODULES:
        offending = {name for name in imported if name == forbidden or name.startswith(forbidden + ".")}
        assert not offending, f"{path.relative_to(ROOT)} imports forbidden module(s): {offending}"


def test_anthropic_is_imported_somewhere_in_narrative():
    """Sanity check the test itself isn't vacuous — anthropic really is used,
    just only where it's allowed."""
    generator = (ROOT / "src" / "narrative" / "generator.py").read_text(encoding="utf-8")
    assert "import anthropic" in generator
