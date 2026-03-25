from __future__ import annotations

from sgm.domain.models import (
    ApprovalResult,
    ContextResponse,
    GoverningSpec,
    Proposal,
    ProposalListResult,
    ProposeResult,
    RejectResult,
    SpecDelta,
    SyncFilesResult,
    SyncSpecResult,
    ValidationReport,
    ValidationResult,
    ValidationSummary,
)


def render_context(response: ContextResponse) -> str:
    if not response.indexed:
        return "[SKIP] not indexed"
    if not response.specs:
        return "[SKIP] no governing specs"

    lines: list[str] = [f"[SPECS] {len(response.specs)} governing"]
    spec_ids: list[str] = []
    for spec in response.specs:
        spec_ids.append(spec.id)
        lines.extend(_render_governing_spec(spec=spec))
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()

    if response.siblings:
        joined_spec_ids: str = ", ".join(spec_ids)
        lines.append("")
        lines.append(
            f"[SIBLINGS] {len(response.siblings)} other files under {joined_spec_ids}"
        )
        lines.extend(response.siblings)
    return "\n".join(lines)


def _render_governing_spec(spec: GoverningSpec) -> list[str]:
    lines: list[str] = [
        f"{spec.id} v{spec.version} {spec.title} (priority={spec.priority})"
    ]
    for text_line in spec.text.strip().splitlines():
        lines.append(f"  {text_line}")
    if (
        spec.total_checks is not None
        and spec.total_checks > 0
        and spec.compliance_score is not None
    ):
        compliance_line: str = (
            f"  compliance={spec.compliance_score:.2f} "
            f"({spec.passed_checks}/{spec.total_checks} checks)"
        )
        if spec.compliance_score < spec.warn_below:
            compliance_line += f" ⚠ below {spec.warn_below:.2f}"
        lines.append(compliance_line)
    if spec.spec_delta is not None:
        lines.extend(_render_spec_delta(spec.spec_delta))
    return lines


def render_validation(
    report: ValidationReport,
    recorded: bool,
    previous_scores: dict[str, float] | None = None,
    updated_scores: dict[str, tuple[float, int, int]] | None = None,
) -> str:
    all_summaries: tuple[ValidationSummary, ...] = report.spec_summaries
    if not all_summaries:
        return "[SKIP] no governing specs"

    all_results = [result for summary in all_summaries for result in summary.results]
    failures = [result for result in all_results if result.outcome != "pass"]
    error_count: int = sum(
        1
        for result in failures
        if result.outcome == "fail" and result.assertion.severity == "error"
    )
    warning_count: int = sum(
        1
        for result in failures
        if (
            (result.outcome != "pass" and result.assertion.severity == "warning")
            or result.outcome == "inconclusive"
        )
    )
    record_suffix: str = " (recorded)" if recorded else ""
    lines: list[str] = []
    if not failures:
        lines.append(f"[PASS] {len(all_results)}/{len(all_results)} assertions{record_suffix}")
    else:
        lines.append(
            f"[FAIL] {len(failures)}/{len(all_results)} "
            f"({error_count} error, {warning_count} warning){record_suffix}"
        )
    for summary in all_summaries:
        for result in summary.results:
            lines.append(_render_validation_result(result=result))
    for spec_delta in report.spec_deltas:
        lines.extend(_render_spec_delta(spec_delta))
    if recorded and previous_scores is not None and updated_scores is not None:
        for spec_id, (score, passed, total) in updated_scores.items():
            previous_score: float | None = previous_scores.get(spec_id)
            if previous_score is None:
                lines.append(f"{spec_id} compliance: {score:.2f} ({passed}/{total} checks)")
            else:
                lines.append(
                    f"{spec_id} compliance: {previous_score:.2f} → {score:.2f} "
                    f"({passed}/{total} checks)"
                )
    return "\n".join(lines)


def _render_spec_delta(spec_delta: SpecDelta) -> list[str]:
    status_suffix: str = (
        "changed since last ingest"
        if spec_delta.current_exists
        else "was removed since last ingest"
    )
    return [
        f"[SPEC-DELTA] {spec_delta.spec_id} {spec_delta.source_path} {status_suffix}",
        *spec_delta.diff_lines,
    ]


def _render_validation_result(result: ValidationResult) -> str:
    assertion = result.assertion
    if result.outcome == "pass":
        return f"  ✓ {assertion.id} {assertion.rule}"
    if result.outcome == "inconclusive":
        return (
            f"  ? {assertion.id} warning {assertion.rule} — "
            f"{result.details or 'inconclusive'}"
        )
    lines: list[str] = [
        f"  ✗ {assertion.id} {assertion.severity:<8s} {assertion.rule} — {result.details}"
    ]
    if assertion.hint is not None:
        lines.append(f"    hint: {assertion.hint}")
    return "\n".join(lines)


def render_sync_files(result: SyncFilesResult) -> str:
    return f"indexed {result.scanned_paths} paths under {result.root}"


def render_sync_spec(result: SyncSpecResult) -> str:
    return (
        f"ingested {result.spec_id}, {result.assertion_count} assertions, "
        f"governs {result.governed_count} files matching {list(result.selectors)}"
    )


def render_propose(result: ProposeResult) -> str:
    if not result.created:
        return f"[SKIP] {result.path} already governed by {result.spec_id}"
    title_suffix: str = f" {result.spec_title}" if result.spec_title is not None else ""
    return "\n".join(
        [
            f"[PROPOSED] {result.proposal_id}",
            f"  spec: {result.spec_id}{title_suffix}",
            f"  file: {result.path}",
            f"  reason: {result.reason}",
            "  status: pending",
            "  review: include in next PR for approval",
        ]
    )


def render_proposals(result: ProposalListResult) -> str:
    if not result.proposals:
        label: str = result.status_filter.upper() if result.status_filter is not None else "ALL"
        return f"[{label}] 0 proposals"
    label = result.status_filter.upper() if result.status_filter is not None else "ALL"
    lines: list[str] = [f"[{label}] {len(result.proposals)} proposals"]
    for proposal in result.proposals:
        lines.extend(_render_proposal(proposal=proposal))
    return "\n".join(lines)


def _render_proposal(proposal: Proposal) -> list[str]:
    lines: list[str] = [
        f"{proposal.id}  {proposal.spec_id} → {proposal.path}",
        f'  "{proposal.reason}"',
    ]
    if proposal.review_reason is not None:
        lines.append(f"  review_reason: {proposal.review_reason}")
    return lines


def render_approval(result: ApprovalResult) -> str:
    return "\n".join(
        [
            f"[APPROVED] {result.proposal_id}",
            f"  {result.spec_id} now governs {result.path}",
        ]
    )


def render_rejection(result: RejectResult) -> str:
    lines: list[str] = [f"[REJECTED] {result.proposal_id}"]
    if result.review_reason is not None:
        lines.append(f"  reason: {result.review_reason}")
    return "\n".join(lines)
