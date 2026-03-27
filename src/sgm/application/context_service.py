from __future__ import annotations

from dataclasses import dataclass, replace

from sgm.adapters.repository import GraphRepository
from sgm.adapters.system import SystemAdapter
from sgm.domain.models import (
    FocusConflict,
    FocusWarning,
    GoverningSpec,
    RelatedDecision,
    RepoContext,
    SpecContextResponse,
    SpecDelta,
)
from sgm.domain.selectors import matches_selector
from sgm.domain.spec_deltas import build_spec_delta


@dataclass(slots=True)
class ContextService:
    repo_context: RepoContext
    graph_repository: GraphRepository
    system: SystemAdapter

    def context(self, spec_ref: str, force: bool = False) -> SpecContextResponse:
        response: SpecContextResponse = self.graph_repository.get_context(spec_ref)
        spec: GoverningSpec = self._with_spec_deltas((response.spec,))[0]
        focus_warning: FocusWarning | None = None
        if not force:
            focus_warning = self._build_focus_warning(
                target_response=response,
                changed_files=self.system.changed_files(self.repo_context.root),
            )
        return SpecContextResponse(
            spec=spec,
            decisions=self._active_decisions(response.decisions),
            governed_files=response.governed_files,
            pending_proposals=response.pending_proposals,
            focus_warning=focus_warning,
        )

    def _with_spec_deltas(
        self,
        specs: tuple[GoverningSpec, ...],
    ) -> tuple[GoverningSpec, ...]:
        enriched_specs: list[GoverningSpec] = []
        for spec in specs:
            spec_delta: SpecDelta | None = build_spec_delta(
                spec_id=spec.id,
                source_path=spec.source_path,
                previous_text=spec.previous_source_text,
                current_text=spec.source_text,
            )
            enriched_specs.append(replace(spec, spec_delta=spec_delta))
        return tuple(enriched_specs)

    def _active_decisions(
        self,
        decisions: tuple[RelatedDecision, ...],
    ) -> tuple[RelatedDecision, ...]:
        return decisions

    def _build_focus_warning(
        self,
        target_response: SpecContextResponse,
        changed_files: tuple[str, ...],
    ) -> FocusWarning | None:
        if not changed_files:
            return None

        conflicts: list[FocusConflict] = []
        for spec_ref in self.graph_repository.list_active_specs():
            other_response = self.graph_repository.get_context(spec_ref)
            if other_response.spec.id == target_response.spec.id:
                continue
            conflicting_files = tuple(
                path
                for path in changed_files
                if self._is_in_scope(other_response, path)
            )
            if conflicting_files:
                conflicts.append(
                    FocusConflict(
                        spec_id=other_response.spec.id,
                        source_path=other_response.spec.source_path,
                        changed_files=conflicting_files,
                    )
                )
        if not conflicts:
            return None
        conflicts.sort(key=lambda conflict: (conflict.spec_id, conflict.source_path))
        return FocusWarning(
            target_spec_id=target_response.spec.id,
            conflicts=tuple(conflicts),
        )

    def _is_in_scope(self, response: SpecContextResponse, path: str) -> bool:
        if path == response.spec.source_path or path in response.governed_files:
            return True
        return any(
            matches_selector(path=path, selector=selector)
            for selector in response.spec.selectors
        )
