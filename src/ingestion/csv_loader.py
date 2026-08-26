"""Load sample_holdings.csv into typed, Decimal-valued rows (BUILD_PLAN.md Step 2).

The compute layer never reads this CSV directly (CLAUDE.md section 3.4) — only
this module does, and only during ingestion, to build Position nodes in the
graph (Step 3).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class HoldingRow:
    instrument_id: str
    instrument_name: str
    asset_class: str
    issuer_name: str
    issuer_type: str
    parent_issuer: str | None
    credit_rating: str | None
    downgraded_from: str | None
    market_value_sgd: Decimal
    modified_duration: Decimal
    source_line: int  # provenance: physical line number in the CSV file


def _clean(value: str) -> str | None:
    value = value.strip()
    return value or None


def load_holdings(csv_path: str | Path) -> list[HoldingRow]:
    rows: list[HoldingRow] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for record in reader:
            rows.append(
                HoldingRow(
                    instrument_id=record["instrument_id"].strip(),
                    instrument_name=record["instrument_name"].strip(),
                    asset_class=record["asset_class"].strip(),
                    issuer_name=record["issuer_name"].strip(),
                    issuer_type=record["issuer_type"].strip(),
                    parent_issuer=_clean(record["parent_issuer"]),
                    credit_rating=_clean(record["credit_rating"]),
                    downgraded_from=_clean(record["downgraded_from"]),
                    market_value_sgd=Decimal(record["market_value_sgd"].strip()),
                    modified_duration=Decimal(record["modified_duration"].strip()),
                    source_line=reader.line_num,
                )
            )
    return rows


if __name__ == "__main__":
    default_path = Path(__file__).resolve().parents[2] / "sample_docs" / "sample_holdings.csv"
    for holding in load_holdings(default_path):
        print(f"L{holding.source_line}: {holding.instrument_id} "
              f"{holding.asset_class!r} SGD {holding.market_value_sgd} "
              f"dur={holding.modified_duration}")
