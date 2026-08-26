"""Reconcile computed figures against Firm A's answer key (BUILD_PLAN.md Step 9).

CLAUDE.md constraint 4: `evaluate` diffs every figure against
firm_A_answer_key.xlsx. src/reconcile/ is not one of the firm-name-restricted
packages (CLAUDE.md section 3.1 only restricts src/compute, src/graph,
src/ingestion) — reconciling against a named firm's answer key, and knowing
firm_B_brief.md's documented deltas, is exactly this module's job.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import openpyxl

# Row layout matches report_template.xlsx / firm_A_answer_key.xlsx exactly
# (see src/compute/excel_report.py's FIGURE_ROW — same source document).
ANSWER_KEY_ROW = {
    "sgs_allocation": 2,
    "mas_bills_allocation": 3,
    "ig_corporate_allocation": 4,
    "high_yield_allocation": 5,
    "fx_bonds_allocation": 6,
    "structured_credit_allocation": 7,
    "cash_allocation": 8,
    "aggregate_non_ig": 9,
    "single_issuer_concentration": 10,
    "gre_concentration": 11,
    "liquidity_ratio": 12,
    "portfolio_duration": 13,
    "portfolio_dv01": 14,
}

# firm_B_brief.md's documented deltas — the only figures allowed to differ
# from Firm A. No separate answer-key workbook was provided for Firm B, so
# `firm_b_reference` derives one: Firm A's answer key with these overridden.
FIRM_B_KNOWN_DIFFERENCES = {
    "aggregate_non_ig": {"value": "21.0%", "status": "BREACH", "limit": "max 20%"},
    "gre_concentration": {"value": "13.0%", "status": "BREACH", "limit": "max 12%"},
}


@dataclass(frozen=True)
class ReconciliationRow:
    figure: str
    expected_value: str
    actual_value: str
    expected_status: str
    actual_status: str
    passed: bool


def read_answer_key(path: str | Path) -> dict[str, dict[str, str]]:
    workbook = openpyxl.load_workbook(path)
    worksheet = workbook.active
    answer_key = {}
    for figure_name, row in ANSWER_KEY_ROW.items():
        answer_key[figure_name] = {
            "value": worksheet.cell(row=row, column=3).value,
            "limit": worksheet.cell(row=row, column=4).value,
            "utilization": worksheet.cell(row=row, column=5).value,
            "status": worksheet.cell(row=row, column=6).value,
        }
    return answer_key


def firm_b_reference(firm_a_answer_key: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Firm A's answer key with the three documented differences overridden.

    Utilization is intentionally excluded from the override rows and not
    compared for Firm B at all — every row's utilization format differs by
    design (percent vs bps), not because the underlying figure is wrong;
    that's covered separately (see tests/test_figures_firm_b.py).
    """
    reference = {name: dict(row) for name, row in firm_a_answer_key.items()}
    for name, override in FIRM_B_KNOWN_DIFFERENCES.items():
        reference[name] = {**reference[name], **override}
    return reference


def reconcile(reports: list[dict], reference: dict[str, dict[str, str]]) -> list[ReconciliationRow]:
    rows = []
    for report in reports:
        name = report["figure"]
        expected = reference.get(name)
        actual_value = report.get("value", "")
        actual_status = report.get("status", "")

        if expected is None:
            rows.append(ReconciliationRow(name, "?", actual_value, "?", actual_status, passed=False))
            continue

        passed = actual_value == expected["value"] and actual_status == expected["status"] and report.get("limit") == expected.get("limit")
        rows.append(ReconciliationRow(name, expected["value"], actual_value, expected["status"], actual_status, passed))

    return rows
