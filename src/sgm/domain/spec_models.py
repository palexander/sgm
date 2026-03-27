from __future__ import annotations

from dataclasses import dataclass

from sgm.domain.core_models import SpecStatus


@dataclass(frozen=True, slots=True)
class GovernanceSelector:
    selector: str
    priority: int


@dataclass(frozen=True, slots=True)
class SpecDocument:
    id: str
    source_path: str
    source_text: str
    title: str
    version: int
    text: str
    status: SpecStatus
    author: str
    governs: tuple[GovernanceSelector, ...]


@dataclass(frozen=True, slots=True)
class SpecDelta:
    spec_id: str
    source_path: str
    diff_lines: tuple[str, ...]
    current_exists: bool
    summary_lines: tuple[str, ...]
    cleanup_required: bool


@dataclass(frozen=True, slots=True)
class GoverningSpec:
    id: str
    source_path: str
    source_text: str
    previous_source_text: str | None
    has_local_snapshot_history: bool
    title: str
    version: int
    text: str
    priority: int
    selectors: tuple[str, ...]
    spec_delta: SpecDelta | None = None
