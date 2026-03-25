from __future__ import annotations

from sgm.domain.models import ComplianceSnapshot
from sgm.domain.scoring import compute_score, merge_compliance


def test_compute_score_uses_warning_weight() -> None:
    assert compute_score(passed_checks=2, failed_errors=1, failed_warnings=2) == 2 / 3.5


def test_merge_compliance_accumulates_counts() -> None:
    merged = merge_compliance(
        previous=ComplianceSnapshot(
            total_checks=2,
            passed_checks=1,
            failed_errors=1,
            failed_warnings=0,
            score=0.5,
        ),
        total_checks=2,
        passed_checks=2,
        failed_errors=0,
        failed_warnings=0,
    )

    assert merged.total_checks == 4
    assert merged.passed_checks == 3
    assert merged.failed_errors == 1
    assert merged.failed_warnings == 0
    assert merged.score == 0.75

