from __future__ import annotations

from sgm.domain.models import Proposal, SpecDelta


def render_spec_delta(spec_delta: SpecDelta) -> list[str]:
    status_suffix: str = (
        "changed since last ingest"
        if spec_delta.current_exists
        else "was removed since last ingest"
    )
    return [
        f"[SPEC-DELTA] {spec_delta.spec_id} {spec_delta.source_path} {status_suffix}",
        *spec_delta.diff_lines,
    ]


def render_proposal(proposal: Proposal) -> list[str]:
    lines: list[str] = [
        f"{proposal.id}  {proposal.spec_id} → {proposal.path}",
        f'  "{proposal.reason}"',
    ]
    if proposal.review_reason is not None:
        lines.append(f"  review_reason: {proposal.review_reason}")
    return lines
