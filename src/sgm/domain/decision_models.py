from __future__ import annotations

from dataclasses import dataclass

from sgm.domain.core_models import DecisionStatus


@dataclass(frozen=True, slots=True)
class DecisionSelector:
    selector: str


@dataclass(frozen=True, slots=True)
class DecisionDocument:
    id: str
    source_path: str
    source_text: str
    title: str
    status: DecisionStatus
    context: str
    decision: str
    consequences: str
    touches: tuple[DecisionSelector, ...]


@dataclass(frozen=True, slots=True)
class RelatedDecision:
    id: str
    title: str
    status: DecisionStatus
    context: str
    decision: str
    consequences: str
