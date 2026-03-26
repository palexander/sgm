from __future__ import annotations

from sgm.domain.models import (
    ApprovalResult,
    InitResult,
    PersistResult,
    ProposalListResult,
    ProposeResult,
    RejectResult,
    SyncDecisionResult,
    SyncFilesResult,
    SyncSpecResult,
)
from sgm.domain.render_shared import render_proposal


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


def render_persist(result: PersistResult) -> str:
    if result.persisted_validations > 0:
        return (
            f"persisted {result.persisted_proposals} proposals and "
            f"{result.persisted_validations} validation records"
        )
    return f"persisted {result.persisted_proposals} proposals"


def render_init(result: InitResult) -> str:
    lines: list[str] = ["[INIT] sgm workspace prepared"]
    if result.created_directories:
        lines.append(f"directories: {', '.join(result.created_directories)}")
    if result.created_files:
        lines.append(f"created: {', '.join(result.created_files)}")
    if result.updated_files:
        lines.append(f"updated: {', '.join(result.updated_files)}")
    if result.offers:
        lines.append("[OFFERS]")
        for offer in result.offers:
            lines.append(f"{offer.target}: {offer.message}")
    return "\n".join(lines)


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
