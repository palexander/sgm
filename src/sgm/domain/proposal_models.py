from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sgm.domain.core_models import ProposalStatus


@dataclass(frozen=True, slots=True)
class Proposal:
    id: str
    spec_id: str
    path: str
    reason: str
    status: ProposalStatus
    created_at: datetime
    reviewed_at: datetime | None
    review_reason: str | None


@dataclass(frozen=True, slots=True)
class ProposeResult:
    created: bool
    proposal_id: str | None
    spec_id: str
    spec_title: str | None
    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class ProposalListResult:
    proposals: tuple[Proposal, ...]
    status_filter: ProposalStatus | None


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    proposal_id: str
    spec_id: str
    path: str


@dataclass(frozen=True, slots=True)
class RejectResult:
    proposal_id: str
    review_reason: str | None
