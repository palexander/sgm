from __future__ import annotations

from dataclasses import dataclass, replace

from sgm.adapters.repository import GraphRepository
from sgm.adapters.system import SystemAdapter
from sgm.domain.models import (
    FocusConflict,
    FocusWarning,
    GoverningSpec,
    ReadRequirement,
    RelatedDecision,
    RepoContext,
    SpecContextResponse,
    SpecDelta,
)
from sgm.domain.spec_deltas import build_spec_delta


@dataclass(slots=True)
class ContextService:
    repo_context: RepoContext
    graph_repository: GraphRepository
    system: SystemAdapter

    def context(self, spec_ref: str, force: bool = False) -> SpecContextResponse:
        response = self.graph_repository.get_context(spec_ref)
        read_specs = self._with_read_specs(response.read_specs)
        target_spec = next(
            requirement.spec
            for requirement in read_specs
            if requirement.role == "target"
        )
        focus_warning: FocusWarning | None = None
        interim_response = SpecContextResponse(
            spec=target_spec,
            read_specs=read_specs,
            decisions=self._active_decisions(response.decisions),
            editable_files=response.editable_files,
            delegated_files=response.delegated_files,
            coordination_files=response.coordination_files,
            pending_proposals=response.pending_proposals,
            next_steps=response.next_steps,
        )
        if not force:
            focus_warning = self._build_focus_warning(
                target_response=interim_response,
                changed_files=self.system.changed_files(self.repo_context.root),
            )
        return SpecContextResponse(
            spec=target_spec,
            read_specs=read_specs,
            decisions=self._active_decisions(response.decisions),
            editable_files=response.editable_files,
            delegated_files=response.delegated_files,
            coordination_files=response.coordination_files,
            pending_proposals=response.pending_proposals,
            next_steps=response.next_steps,
            focus_warning=focus_warning,
        )

    def _with_spec_deltas(
        self,
        specs: tuple[GoverningSpec, ...],
    ) -> tuple[GoverningSpec, ...]:
        enriched_specs: list[GoverningSpec] = []
        for spec in specs:
            fallback_diff_lines: tuple[str, ...] | None = None
            if spec.previous_source_text is None and not spec.has_local_snapshot_history:
                fallback_diff_lines = self.system.git_diff(
                    self.repo_context.root,
                    spec.source_path,
                )
            spec_delta: SpecDelta | None = build_spec_delta(
                spec_id=spec.id,
                source_path=spec.source_path,
                previous_text=spec.previous_source_text,
                current_text=spec.source_text,
                fallback_diff_lines=fallback_diff_lines,
            )
            enriched_specs.append(replace(spec, spec_delta=spec_delta))
        return tuple(enriched_specs)

    def _with_read_specs(
        self,
        read_specs: tuple[ReadRequirement, ...],
    ) -> tuple[ReadRequirement, ...]:
        enriched_specs = self._with_spec_deltas(
            tuple(requirement.spec for requirement in read_specs)
        )
        by_spec_id = {spec.id: spec for spec in enriched_specs}
        return tuple(
            replace(requirement, spec=by_spec_id[requirement.spec.id])
            for requirement in read_specs
        )

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
                and not self._is_permitted_overlap(target_response, other_response, path)
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
        return path == response.spec.source_path or path in response.editable_files

    def _is_permitted_overlap(
        self,
        target_response: SpecContextResponse,
        other_response: SpecContextResponse,
        path: str,
    ) -> bool:
        if any(
            delegation.path == path and delegation.owner_spec_id == other_response.spec.id
            for delegation in target_response.delegated_files
        ):
            return True
        if any(
            delegation.path == path and delegation.owner_spec_id == target_response.spec.id
            for delegation in other_response.delegated_files
        ):
            return True
        if any(
            coordination.path == path and coordination.owner_spec_id == other_response.spec.id
            for coordination in target_response.coordination_files
        ):
            return True
        return any(
            coordination.path == path and coordination.owner_spec_id == target_response.spec.id
            for coordination in other_response.coordination_files
        )
