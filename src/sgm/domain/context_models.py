from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sgm.domain.decision_models import RelatedDecision
from sgm.domain.proposal_models import Coordination, Delegation, Proposal
from sgm.domain.spec_models import GoverningSpec


@dataclass(frozen=True, slots=True)
class FocusConflict:
    spec_id: str
    source_path: str
    changed_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FocusWarning:
    target_spec_id: str
    conflicts: tuple[FocusConflict, ...]


@dataclass(frozen=True, slots=True)
class ReadRequirement:
    spec: GoverningSpec
    role: Literal["target", "owner"]
    paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SpecContextResponse:
    spec: GoverningSpec
    read_specs: tuple[ReadRequirement, ...]
    decisions: tuple[RelatedDecision, ...]
    editable_files: tuple[str, ...]
    delegated_files: tuple[Delegation, ...]
    coordination_files: tuple[Coordination, ...]
    pending_proposals: tuple[Proposal, ...]
    next_steps: tuple[str, ...]
    focus_warning: FocusWarning | None = None
