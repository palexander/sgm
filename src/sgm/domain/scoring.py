from __future__ import annotations

from sgm.domain.models import ComplianceSnapshot


def compute_score(
    passed_checks: int,
    failed_errors: int,
    failed_warnings: int,
) -> float:
    denominator: float = passed_checks + failed_errors + (0.25 * failed_warnings)
    if denominator == 0:
        return 1.0
    return passed_checks / denominator


def merge_compliance(
    previous: ComplianceSnapshot,
    total_checks: int,
    passed_checks: int,
    failed_errors: int,
    failed_warnings: int,
) -> ComplianceSnapshot:
    next_total: int = previous.total_checks + total_checks
    next_passed: int = previous.passed_checks + passed_checks
    next_failed_errors: int = previous.failed_errors + failed_errors
    next_failed_warnings: int = previous.failed_warnings + failed_warnings
    return ComplianceSnapshot(
        total_checks=next_total,
        passed_checks=next_passed,
        failed_errors=next_failed_errors,
        failed_warnings=next_failed_warnings,
        score=compute_score(next_passed, next_failed_errors, next_failed_warnings),
    )

