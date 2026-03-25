from __future__ import annotations

from dataclasses import dataclass

from sgm.domain.decision_models import RelatedDecision
from sgm.domain.proposal_models import Proposal
from sgm.domain.spec_models import GoverningSpec


@dataclass(frozen=True, slots=True)
class SpecContextResponse:
    spec: GoverningSpec
    decisions: tuple[RelatedDecision, ...]
    governed_files: tuple[str, ...]
    pending_proposals: tuple[Proposal, ...]
