"""Extract numeric limits from the guidelines PDF via regex (BUILD_PLAN.md Step 2).

CLAUDE.md section 9 is explicit: numeric limit extraction must use regex/table
parsing, never the LLM — the guideline tables have a fixed, known shape, so
each limit is matched by an explicit pattern anchored to its row label,
rather than inferred generically. If a required limit can't be found, this
raises loudly instead of silently omitting it (CLAUDE.md section 3.5).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pdfplumber

from src.ingestion.chunker import Chunk, chunk_pdf


@dataclass(frozen=True)
class ExtractedLimit:
    name: str
    unit: str  # "percent" | "years" | "sgd_per_bp"
    min_value: Decimal | None
    max_value: Decimal | None
    page: int
    chunk_id: str
    raw_text: str


@dataclass(frozen=True)
class RetentionRow:
    report_name: str
    frequency: str
    recipients: str
    retention: str | None  # None when the source column couldn't be parsed cleanly
    raw_text: str


@dataclass(frozen=True)
class ExtractedBreachAction:
    risk_metric_name: str  # matches an ExtractedLimit.name, e.g. "portfolio_duration"
    text: str  # verbatim breach action, e.g. "PM notification within 1h"
    page: int
    chunk_id: str


@dataclass(frozen=True)
class ParsedGuidelines:
    limits: list[ExtractedLimit]
    breach_actions: list[ExtractedBreachAction]
    retention_rows: list[RetentionRow]


# Each pattern is anchored to the row's label text, matching CLAUDE.md section 2
# and 3.1-3.3 verbatim. Unrecognised unicode glyphs (en-dash, <=) come out of
# pdfplumber as a single "�" replacement character, hence the bare `\S`
# standing in for punctuation between numbers.
_RANGE_PATTERNS = [
    ("sgs_allocation", "percent", r"Singapore Government Securities \(SGS\)\s+(\d+)%\s+(\d+)%"),
    ("mas_bills_allocation", "percent", r"\bMAS Bills\s+(\d+)%\s+(\d+)%"),
    ("ig_corporate_allocation", "percent", r"Investment Grade Corporate Bonds\s+(\d+)%\s+(\d+)%"),
    ("high_yield_allocation", "percent", r"High Yield Bonds\s+(\d+)%\s+(\d+)%"),
    ("fx_bonds_allocation", "percent", r"Foreign Currency Bonds \(hedged\)\s+(\d+)%\s+(\d+)%"),
    ("structured_credit_allocation", "percent", r"Structured Credit \(ABS/MBS\)\s+(\d+)%\s+(\d+)%"),
    ("cash_allocation", "percent", r"Cash\s*(?:&amp;|&)\s*Cash Equivalents\s+(\d+)%\s+(\d+)%"),
    ("portfolio_duration", "years", r"Modified Duration\s+(\d+\.\d+)\s*\S\s*(\d+\.\d+)\s*years"),
]

_MAX_ONLY_PATTERNS = [
    (
        "aggregate_non_ig",
        "percent",
        r"non-investment-grade instruments \(High Yield \+ Structured Credit\) must not exceed\s+(\d+)%\s+of NAV",
    ),
    (
        "single_issuer_concentration",
        "percent",
        r"No single issuer \(excluding Singapore Government\) may represent more\s+than\s+(\d+)%\s+of NAV",
    ),
    ("gre_concentration", "percent", r"Government-related entities \(GREs\) are capped at\s+(\d+)%\s+per issuer"),
    ("portfolio_dv01", "sgd_per_bp", r"Portfolio DV01\s+\S\s*SGD\s+([\d,]+)\s+per bp"),
]

_MIN_ONLY_PATTERNS = [
    (
        "liquidity_ratio",
        "percent",
        r"Liquid assets \(SGS \+ MAS Bills \+ Cash\) must constitute a minimum of\s+(\d+)%\s+of NAV",
    ),
]

_ALL_LIMIT_NAMES = (
    [n for n, _, _ in _RANGE_PATTERNS]
    + [n for n, _, _ in _MAX_ONLY_PATTERNS]
    + [n for n, _, _ in _MIN_ONLY_PATTERNS]
)

# Only the two 3.1 rows that have a corresponding numeric Limit above need a
# breach action for the graph (Step 3) — the other market-risk rows (VaR, ES,
# etc.) aren't turned into graph nodes at all, so their breach text isn't
# needed. Text extraction is clean here (unlike the retention table).
_BREACH_ACTION_PATTERNS = [
    ("portfolio_duration", r"Modified Duration\s+\d+\.\d+\s*\S\s*\d+\.\d+\s*years\s+Daily\s+([^\n]+)"),
    ("portfolio_dv01", r"Portfolio DV01\s+\S\s*SGD\s+[\d,]+\s+per bp\s+Daily\s+([^\n]+)"),
]

_RETENTION_VALUE_PATTERN = re.compile(r"\b(\d+\s*years?|Permanent)\b")


def _to_decimal(raw: str) -> Decimal:
    return Decimal(raw.replace(",", ""))


def parse_guidelines(pdf_path: str | Path) -> ParsedGuidelines:
    chunks = chunk_pdf(pdf_path)
    found: dict[str, ExtractedLimit] = {}
    breach_actions: dict[str, ExtractedBreachAction] = {}

    for chunk in chunks:
        text = chunk.text

        for metric_name, pattern in _BREACH_ACTION_PATTERNS:
            if metric_name in breach_actions:
                continue
            m = re.search(pattern, text)
            if m:
                breach_actions[metric_name] = ExtractedBreachAction(
                    risk_metric_name=metric_name,
                    text=m.group(1).strip(),
                    page=chunk.page,
                    chunk_id=chunk.chunk_id,
                )

        for name, unit, pattern in _RANGE_PATTERNS:
            if name in found:
                continue
            m = re.search(pattern, text)
            if m:
                found[name] = ExtractedLimit(
                    name=name,
                    unit=unit,
                    min_value=_to_decimal(m.group(1)),
                    max_value=_to_decimal(m.group(2)),
                    page=chunk.page,
                    chunk_id=chunk.chunk_id,
                    raw_text=m.group(0),
                )

        for name, unit, pattern in _MAX_ONLY_PATTERNS:
            if name in found:
                continue
            m = re.search(pattern, text)
            if m:
                found[name] = ExtractedLimit(
                    name=name,
                    unit=unit,
                    min_value=None,
                    max_value=_to_decimal(m.group(1)),
                    page=chunk.page,
                    chunk_id=chunk.chunk_id,
                    raw_text=m.group(0),
                )

        for name, unit, pattern in _MIN_ONLY_PATTERNS:
            if name in found:
                continue
            m = re.search(pattern, text)
            if m:
                found[name] = ExtractedLimit(
                    name=name,
                    unit=unit,
                    min_value=_to_decimal(m.group(1)),
                    max_value=None,
                    page=chunk.page,
                    chunk_id=chunk.chunk_id,
                    raw_text=m.group(0),
                )

    missing = [n for n in _ALL_LIMIT_NAMES if n not in found]
    if missing:
        raise ValueError(f"failed to extract required limits from guidelines PDF: {missing}")

    missing_breach = [n for n, _ in _BREACH_ACTION_PATTERNS if n not in breach_actions]
    if missing_breach:
        raise ValueError(f"failed to extract required breach actions from guidelines PDF: {missing_breach}")

    limits = [found[n] for n in _ALL_LIMIT_NAMES]
    breach_action_list = [breach_actions[n] for n, _ in _BREACH_ACTION_PATTERNS]
    retention_rows = _parse_retention_table(pdf_path)

    return ParsedGuidelines(limits=limits, breach_actions=breach_action_list, retention_rows=retention_rows)


def _parse_retention_table(pdf_path: str | Path) -> list[RetentionRow]:
    """Best-effort extraction of the section 4 reporting/retention table.

    The source PDF has overlapping text runs in this table's rightmost
    columns (visible as interleaved characters in the raw extraction, e.g.
    "du7ra ytieoanr,s DV01" for what should read "duration, DV01" / "7
    years"). `retention` is left as None, with the full row preserved in
    `raw_text`, whenever it can't be matched cleanly — this is metadata, not
    a compliance limit, so a missed value here doesn't affect any figure.
    """
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if not table or not table[0]:
                    continue
                header = [c.strip() if c else "" for c in table[0]]
                if not header or header[0] != "Report Name":
                    continue

                rows: list[RetentionRow] = []
                for raw_row in table[1:]:
                    cells = [c.strip() if c else "" for c in raw_row]
                    if len(cells) < 3:
                        continue
                    tail = " ".join(cells[3:])
                    match = _RETENTION_VALUE_PATTERN.search(tail)
                    rows.append(
                        RetentionRow(
                            report_name=cells[0],
                            frequency=cells[1],
                            recipients=cells[2],
                            retention=match.group(1) if match else None,
                            raw_text=" | ".join(cells),
                        )
                    )
                return rows
    return []


if __name__ == "__main__":
    default_path = Path(__file__).resolve().parents[2] / "sample_docs" / "sample_fund_guidelines.pdf"
    parsed = parse_guidelines(default_path)

    print("=== extracted limits ===")
    for limit in parsed.limits:
        bound = f"{limit.min_value} - {limit.max_value}" if limit.min_value is not None and limit.max_value is not None else (
            f"min {limit.min_value}" if limit.min_value is not None else f"max {limit.max_value}"
        )
        print(f"{limit.name:32s} {bound:16s} {limit.unit:10s} page={limit.page} chunk={limit.chunk_id}")

    print("\n=== extracted breach actions ===")
    for breach in parsed.breach_actions:
        print(f"{breach.risk_metric_name:20s} {breach.text!r} page={breach.page} chunk={breach.chunk_id}")

    print("\n=== retention rows (best-effort) ===")
    for row in parsed.retention_rows:
        print(f"{row.report_name:30s} retention={row.retention!r}")
