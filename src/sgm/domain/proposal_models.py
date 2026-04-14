from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sgm.domain.core_models import ProposalStatus, SharedRecordStatus


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
    owner_spec_id: str | None = None
    owner_spec_title: str | None = None


@dataclass(frozen=True, slots=True)
class ProposalListResult:
    proposals: tuple[Proposal, ...]
    status_filter: ProposalStatus | None


@dataclass(frozen=True, slots=True)
class ProposalReviewItem:
    proposal: Proposal
    spec_title: str
    spec_text: str
    governed_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProposalReviewResult:
    proposals: tuple[ProposalReviewItem, ...]


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    proposal_id: str
    spec_id: str
    path: str


@dataclass(frozen=True, slots=True)
class RejectResult:
    proposal_id: str
    review_reason: str | None


@dataclass(frozen=True, slots=True)
class Delegation:
    id: str
    owner_spec_id: str
    delegate_spec_id: str
    path: str
    reason: str
    status: SharedRecordStatus
    created_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class Coordination:
    id: str
    owner_spec_id: str
    path: str
    reason: str
    status: SharedRecordStatus
    created_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class SharedAllowResult:
    created: bool
    delegation: Delegation


@dataclass(frozen=True, slots=True)
class SharedRevokeResult:
    revoked: bool
    delegation: Delegation


@dataclass(frozen=True, slots=True)
class CoordinationMarkResult:
    created: bool
    coordination: Coordination


@dataclass(frozen=True, slots=True)
class CoordinationUnmarkResult:
    revoked: bool
    coordination: Coordination


@dataclass(frozen=True, slots=True)
class SharedListResult:
    query: str
    spec_id: str | None
    spec_title: str | None
    path: str | None
    owner_spec_id: str | None
    owner_spec_title: str | None
    owned_delegations: tuple[Delegation, ...]
    delegated_to_spec: tuple[Delegation, ...]
    owned_coordination: tuple[Coordination, ...]
    available_coordination: tuple[Coordination, ...]
    path_delegations: tuple[Delegation, ...]
    path_coordination: Coordination | None
