"""Generic aggregation primitives over lists of plain dict records (BUILD_PLAN.md Step 5).

No domain knowledge here — nothing about asset classes, firms, or issuer
types. figures.py supplies the field names and predicates; these functions
just filter/group/sum/average, always with Decimal (CLAUDE.md section 3.3:
never float, never round() — rounding happens only in formatters.py).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Callable, Iterable

Record = dict[str, object]


def filter_by(records: Iterable[Record], predicate: Callable[[Record], bool]) -> list[Record]:
    return [r for r in records if predicate(r)]


def sum_by(records: Iterable[Record], group_by_field: str, value_field: str) -> dict[object, Decimal]:
    """Sum `value_field` within each distinct value of `group_by_field`."""
    totals: dict[object, Decimal] = {}
    for record in records:
        key = record[group_by_field]
        totals[key] = totals.get(key, Decimal(0)) + record[value_field]
    return totals


def weighted_average(records: Iterable[Record], value_field: str, weight_field: str) -> Decimal:
    records = list(records)
    total_weight = sum((r[weight_field] for r in records), Decimal(0))
    if total_weight == 0:
        raise ValueError("cannot compute a weighted average with zero total weight")
    weighted_sum = sum((r[value_field] * r[weight_field] for r in records), Decimal(0))
    return weighted_sum / total_weight
