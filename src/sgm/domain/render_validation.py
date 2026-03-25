from __future__ import annotations

from sgm.domain.models import ValidationReport, ValidationSuiteReport, ValidationWarning
from sgm.domain.render_shared import render_spec_delta


def render_validation(suite: ValidationSuiteReport, recorded: bool) -> str:
    reports: tuple[ValidationReport, ...] = suite.reports
    if not reports:
        return "[SKIP] no active specs"
    if len(reports) == 1:
        return _render_validation_report(report=reports[0], recorded=recorded)

    error_specs: int = sum(1 for report in reports if report.error_files)
    warning_specs: int = sum(
        1 for report in reports if not report.error_files and report.warning_files
    )
    pass_specs: int = len(reports) - error_specs - warning_specs
    record_suffix: str = " (recorded)" if recorded else ""
    lines: list[str] = [
        (
            f"[VALIDATE] {len(reports)} spec(s): "
            f"{pass_specs} pass, {warning_specs} warn, {error_specs} fail{record_suffix}"
        )
    ]
    for report in reports:
        lines.append("")
        lines.extend(_render_validation_report(report=report, recorded=False).splitlines())
    return "\n".join(lines)


def _render_validation_report(report: ValidationReport, recorded: bool) -> str:
    warning_count: int = len(report.warning_files)
    error_count: int = len(report.error_files)
    record_suffix: str = " (recorded)" if recorded else ""
    if error_count > 0:
        lines: list[str] = [
            f"[FAIL] {error_count} changed file(s) outside {report.spec.id}{record_suffix}"
        ]
    elif warning_count > 0:
        lines = [
            (
                f"[WARN] {warning_count} changed file(s) pending governance for "
                f"{report.spec.id}{record_suffix}"
            )
        ]
    elif not report.changed_files:
        lines = [f"[PASS] no changed files for {report.spec.id}{record_suffix}"]
    else:
        lines = [
            (
                f"[PASS] all {len(report.changed_files)} changed file(s) stayed "
                f"within {report.spec.id}{record_suffix}"
            )
        ]
    if report.changed_files:
        lines.append("[CHANGED]")
        lines.extend(report.changed_files)
    if report.warning_files:
        lines.append("[WARNINGS]")
        lines.extend(_render_validation_warning(warning) for warning in report.warning_files)
    if report.error_files:
        lines.append("[ERRORS]")
        lines.extend(report.error_files)
    if report.spec.spec_delta is not None:
        lines.extend(render_spec_delta(report.spec.spec_delta))
    return "\n".join(lines)


def _render_validation_warning(warning: ValidationWarning) -> str:
    return (
        f"{warning.path} "
        f"(proposal {warning.proposal.id}: {warning.proposal.reason})"
    )
