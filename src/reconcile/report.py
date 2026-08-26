"""Print evaluate's three checks: reconciliation, traceability, firewall (BUILD_PLAN.md Step 9)."""
from __future__ import annotations

from src.narrative.firewall import check_narrative
from src.reconcile.compare import ReconciliationRow


def print_reconciliation(rows: list[ReconciliationRow]) -> bool:
    print("=== Reconciliation ===")
    for row in rows:
        marker = "PASS" if row.passed else "FAIL"
        print(
            f"[{marker}] {row.figure:32s} expected={row.expected_value:16s} actual={row.actual_value:16s} "
            f"expected_status={row.expected_status:10s} actual_status={row.actual_status}"
        )
    passed_count = sum(1 for r in rows if r.passed)
    print(f"{passed_count}/{len(rows)} figures reconciled")
    return passed_count == len(rows)


def print_traceability(reports: list[dict]) -> bool:
    print("\n=== Traceability ===")
    passed_count = 0
    for report in reports:
        has_path = bool(report.get("graph_path"))
        has_citation = report.get("citation") is not None
        ok = has_path and has_citation and report.get("status") != "ERROR"
        marker = "PASS" if ok else "FAIL"
        print(f"[{marker}] {report['figure']:32s} graph_path={'yes' if has_path else 'no':4s} citation={'yes' if has_citation else 'no'}")
        passed_count += ok
    print(f"{passed_count}/{len(reports)} figures traceable to source")
    return passed_count == len(reports)


def print_firewall(narrative: str, reports: list[dict]) -> bool:
    print("\n=== Firewall ===")
    if not narrative:
        print("no narrative generated (no ANTHROPIC_API_KEY) - nothing to check, trivially clean")
        return True

    result = check_narrative(narrative, reports)
    if result.passed:
        print("narrative clean - no unexplained numeric tokens")
    else:
        print(f"narrative REJECTED - unexplained tokens: {result.rejected_tokens}")
    return result.passed
