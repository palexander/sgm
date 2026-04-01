from __future__ import annotations

from sgm.domain.proposal_models import Proposal, ProposalReviewItem
from sgm.domain.spec_models import SpecDelta


def render_spec_delta(spec_delta: SpecDelta) -> list[str]:
    status_suffix: str = (
        "changed since last ingest"
        if spec_delta.current_exists
        else "was removed since last ingest"
    )
    lines: list[str] = [
        f"[SPEC-DELTA] {spec_delta.spec_id} {spec_delta.source_path} {status_suffix}",
    ]
    if spec_delta.summary_lines:
        lines.append("[DELTA-SUMMARY]")
        lines.extend(spec_delta.summary_lines)
    lines.extend(spec_delta.diff_lines)
    if spec_delta.cleanup_required:
        lines.append(
            "[CLEANUP] This spec removed behavior. Remove or isolate "
            "obsolete code, tests, and docs instead of keeping parallel "
            "implementations by default."
        )
    return lines


def render_proposal(proposal: Proposal) -> list[str]:
    lines: list[str] = [
        f"{proposal.id}  {proposal.spec_id} → {proposal.path}",
        f'  "{proposal.reason}"',
    ]
    if proposal.review_reason is not None:
        lines.append(f"  review_reason: {proposal.review_reason}")
    return lines


def render_proposal_review(
    review: ProposalReviewItem,
    expanded: bool = False,
    spaced: bool = False,
    spec_excerpt_lines: int | None = None,
) -> list[str]:
    lines: list[str] = [
        f"[REVIEW] {review.proposal.id}",
        f"  spec: {review.proposal.spec_id} {review.spec_title}",
        f"  file: {review.proposal.path}",
        f"  reason: {review.proposal.reason}",
    ]
    if spaced:
        lines.append("")
    lines.append("  spec summary:")
    lines.extend(
        f"    {line}"
        for line in _spec_excerpt(review.spec_text, limit=spec_excerpt_lines)
    )
    if expanded:
        if spaced:
            lines.append("")
        lines.append(f"  [FILES] {len(review.governed_files)} governed")
        lines.extend(f"    {path}" for path in review.governed_files)
    if spaced:
        lines.append("")
    lines.append("  keys: a=approve r[ reason]=reject s=skip g=files q=quit ?=help")
    return lines


def _spec_excerpt(text: str, limit: int | None = 6) -> tuple[str, ...]:
    lines = [line.rstrip() for line in text.strip().splitlines() if line.strip()]
    if limit is None or limit < 0:
        return tuple(lines)
    if len(lines) <= limit:
        return tuple(lines)
    truncated: tuple[str, ...] = tuple(lines[:limit])
    return (*truncated, "[spec excerpt truncated]")
