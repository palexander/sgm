from __future__ import annotations

from sgm.domain.models import (
    ApprovalResult,
    CoordinationMarkResult,
    CoordinationUnmarkResult,
    InitResult,
    ProposalListResult,
    ProposeResult,
    RejectResult,
    SharedAllowResult,
    SharedListResult,
    SharedRevokeResult,
    SyncDecisionResult,
    SyncFilesResult,
    SyncSpecResult,
)
from sgm.domain.proposal_models import Proposal, ProposalReviewItem


def render_sync_files(result: SyncFilesResult) -> str:
    return f"indexed {result.scanned_paths} paths under {result.root}"


def render_sync_spec(result: SyncSpecResult) -> str:
    return (
        f"ingested {result.spec_id}, governs {result.governed_count} files "
        f"matching {list(result.selectors)}"
    )


def render_sync_decision(result: SyncDecisionResult) -> str:
    return (
        f"ingested {result.decision_id}, "
        f"informs {result.informed_count} files matching {list(result.selectors)}"
    )


def render_init(result: InitResult) -> str:
    lines: list[str] = ["[INIT] sgm workspace prepared"]
    if result.created_directories:
        lines.append(f"directories: {', '.join(result.created_directories)}")
    if result.created_files:
        lines.append(f"created: {', '.join(result.created_files)}")
    if result.updated_files:
        lines.append(f"updated: {', '.join(result.updated_files)}")
    if result.installed_hooks:
        lines.append(f"hooks: {', '.join(result.installed_hooks)}")
    if result.offers:
        lines.append("[OFFERS]")
        for offer in result.offers:
            lines.append(f"{offer.target}: {offer.message}")
    return "\n".join(lines)


def render_propose(result: ProposeResult) -> str:
    if not result.created:
        if result.owner_spec_id is not None:
            owner_suffix = (
                f" {result.owner_spec_title}" if result.owner_spec_title is not None else ""
            )
            return "\n".join(
                [
                    f"[BLOCKED] {result.path} is already owned by {result.owner_spec_id}{owner_suffix}",
                    "  ownership change: update the governing spec instead of proposing under another spec",
                    (
                        "  delegated access: ask a human, then record "
                        f"`sgm shared allow {result.owner_spec_id} {result.spec_id} {result.path} \"<reason>\"`"
                    ),
                ]
            )
        if result.proposal_id is not None:
            return f"[SKIP] {result.path} already pending under {result.proposal_id} for {result.spec_id}"
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
        lines.extend(render_proposal(proposal=proposal))
    return "\n".join(lines)


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


def render_shared_allow(result: SharedAllowResult) -> str:
    delegation = result.delegation
    label = "[ALLOWED]" if result.created else "[SKIP]"
    lines = [
        f"{label} {delegation.id}",
        f"  owner: {delegation.owner_spec_id}",
        f"  delegate: {delegation.delegate_spec_id}",
        f"  file: {delegation.path}",
        f"  reason: {delegation.reason}",
        "  ownership: unchanged",
    ]
    if not result.created:
        lines.append("  status: already active")
    return "\n".join(lines)


def render_shared_revoke(result: SharedRevokeResult) -> str:
    delegation = result.delegation
    label = "[REVOKED]" if result.revoked else "[SKIP]"
    lines = [
        f"{label} {delegation.id}",
        f"  owner: {delegation.owner_spec_id}",
        f"  delegate: {delegation.delegate_spec_id}",
        f"  file: {delegation.path}",
    ]
    if not result.revoked:
        lines.append("  status: already inactive")
    return "\n".join(lines)


def render_coordination_mark(result: CoordinationMarkResult) -> str:
    coordination = result.coordination
    label = "[COORDINATION]" if result.created else "[SKIP]"
    lines = [
        f"{label} {coordination.id}",
        f"  owner: {coordination.owner_spec_id}",
        f"  file: {coordination.path}",
        f"  reason: {coordination.reason}",
        "  rule: coordination files are only for follow-through alongside substantive in-scope work",
    ]
    if not result.created:
        lines.append("  status: already active")
    return "\n".join(lines)


def render_coordination_unmark(result: CoordinationUnmarkResult) -> str:
    coordination = result.coordination
    label = "[UNMARKED]" if result.revoked else "[SKIP]"
    lines = [
        f"{label} {coordination.id}",
        f"  owner: {coordination.owner_spec_id}",
        f"  file: {coordination.path}",
    ]
    if not result.revoked:
        lines.append("  status: already inactive")
    return "\n".join(lines)


def render_shared_list(result: SharedListResult) -> str:
    lines: list[str] = [f"[SHARED] {result.query}"]
    if result.spec_id is not None:
        title_suffix = f" {result.spec_title}" if result.spec_title is not None else ""
        lines.append(f"  spec: {result.spec_id}{title_suffix}")
        if result.owned_delegations:
            lines.append(f"  [OWNED-DELEGATIONS] {len(result.owned_delegations)}")
            for delegation in result.owned_delegations:
                lines.append(f"    {delegation.path} -> {delegation.delegate_spec_id}")
        if result.delegated_to_spec:
            lines.append(f"  [DELEGATED-TO-THIS-SPEC] {len(result.delegated_to_spec)}")
            for delegation in result.delegated_to_spec:
                lines.append(f"    {delegation.path} <- {delegation.owner_spec_id}")
        if result.owned_coordination:
            lines.append(f"  [OWNED-COORDINATION] {len(result.owned_coordination)}")
            for coordination in result.owned_coordination:
                lines.append(f"    {coordination.path}")
        if result.available_coordination:
            lines.append(f"  [AVAILABLE-COORDINATION] {len(result.available_coordination)}")
            for coordination in result.available_coordination:
                lines.append(f"    {coordination.path} <- {coordination.owner_spec_id}")
    elif result.path is not None:
        lines.append(f"  file: {result.path}")
        if result.owner_spec_id is not None:
            title_suffix = f" {result.owner_spec_title}" if result.owner_spec_title is not None else ""
            lines.append(f"  owner: {result.owner_spec_id}{title_suffix}")
        else:
            lines.append("  owner: none")
        if result.path_delegations:
            lines.append(f"  [DELEGATIONS] {len(result.path_delegations)}")
            for delegation in result.path_delegations:
                lines.append(f"    {delegation.owner_spec_id} -> {delegation.delegate_spec_id}")
        if result.path_coordination is not None:
            lines.append("  [COORDINATION]")
            lines.append(f"    owner: {result.path_coordination.owner_spec_id}")
            lines.append(f"    reason: {result.path_coordination.reason}")
    if len(lines) == 1:
        lines.append("  no active shared governance records")
    return "\n".join(lines)


def render_proposal_review_prompt(review: ProposalReviewItem, expanded: bool = False) -> str:
    return "\n".join(render_proposal_review(review=review, expanded=expanded))


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
