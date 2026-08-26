"""Reject narrative text containing numbers not traceable to computed figures
(BUILD_PLAN.md Step 8 / CLAUDE.md section 9).

Deterministic token comparison only — "Firewall check | No [LLM] | deterministic
token comparison" per CLAUDE.md section 9. Every numeric token in the
narrative must either appear in the computed figures (value/limit/
utilization strings) or match a whitelisted non-figure pattern (years,
section references, durations with a unit like "24 hours").
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# A whole alnum/./,/- run, e.g. "38,790" or "DV01" or "COR-01" or "45.6".
# Anything containing a letter is an identifier (a figure name like "DV01",
# an instrument code like "COR-01") rather than a numeric claim, and is
# excluded whole — not just the digit run glued to the letter — so "DV01"
# doesn't leak a stray "1" once the "0" (glued to "V") is excluded.
_TOKEN_CANDIDATE = re.compile(r"[A-Za-z0-9][A-Za-z0-9,.\-]*")

_YEAR_PATTERN = re.compile(r"\b(?:19|20)\d{2}\b")
_SECTION_REFERENCE = re.compile(r"\bsection\s+(\d+(?:\.\d+)?)\b", re.IGNORECASE)
_DURATION_WITH_UNIT = re.compile(
    r"\b(\d[\d,]*(?:\.\d+)?)\s*(?:hours?|business\s+days?|calendar\s+days?|days?|years?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FirewallResult:
    passed: bool
    rejected_tokens: list[str]


def _normalize(token: str) -> str:
    return token.replace(",", "")


def _extract_numbers(text: str) -> set[str]:
    numbers: set[str] = set()
    for match in _TOKEN_CANDIDATE.finditer(text):
        token = match.group(0)
        if any(c.isalpha() for c in token):
            continue  # identifier like "DV01" / "COR-01" - not a numeric claim
        cleaned = token.strip(".,")
        if cleaned and any(c.isdigit() for c in cleaned):
            numbers.add(_normalize(cleaned))
    return numbers


def extract_figure_numbers(figures_json: list[dict]) -> set[str]:
    """Every numeric token appearing in the computed figures' own
    value/limit/utilization display strings — the only numbers a narrative
    is allowed to state."""
    numbers: set[str] = set()
    for fig in figures_json:
        if fig.get("status") == "ERROR":
            continue
        for field in ("value", "limit", "utilization"):
            numbers.update(_extract_numbers(fig.get(field) or ""))
    return numbers


def _whitelisted_numbers(text: str) -> set[str]:
    whitelisted: set[str] = set()
    whitelisted.update(_normalize(m) for m in _YEAR_PATTERN.findall(text))
    whitelisted.update(_normalize(m) for m in _SECTION_REFERENCE.findall(text))
    whitelisted.update(_normalize(m) for m in _DURATION_WITH_UNIT.findall(text))
    return whitelisted


def check_narrative(narrative: str, figures_json: list[dict]) -> FirewallResult:
    tokens_in_narrative = _extract_numbers(narrative)
    allowed = extract_figure_numbers(figures_json) | _whitelisted_numbers(narrative)

    rejected = sorted(tokens_in_narrative - allowed)
    return FirewallResult(passed=not rejected, rejected_tokens=rejected)
