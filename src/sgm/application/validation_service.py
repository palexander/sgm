from __future__ import annotations

from dataclasses import dataclass

from sgm.adapters.repository import GraphRepository
from sgm.adapters.system import SystemAdapter
from sgm.application.context_service import ContextService
from sgm.domain.models import (
    RepoContext,
    SpecContextResponse,
    ValidationError,
    ValidationNote,
    ValidationReport,
    ValidationSuiteReport,
    ValidationWarning,
)


@dataclass(slots=True)
class ValidationService:
    repo_context: RepoContext
    graph_repository: GraphRepository
    system: SystemAdapter
    context_service: ContextService

    def validate(
        self,
        spec_ref: str | None,
        record: bool,
        force: bool = False,
    ) -> ValidationSuiteReport:
        changed_files: tuple[str, ...] = self.system.changed_files(self.repo_context.root)
        spec_refs: tuple[str, ...] = (
            self.graph_repository.list_active_specs() if spec_ref is None else (spec_ref,)
        )
        reports = tuple(
            self._validate_spec(
                spec_ref=current_spec_ref,
                changed_files=changed_files,
                record=record,
                force=force if spec_ref is not None else False,
            )
            for current_spec_ref in spec_refs
        )
        return ValidationSuiteReport(reports=reports)

    def _validate_spec(
        self,
        spec_ref: str,
        changed_files: tuple[str, ...],
        record: bool,
        force: bool,
    ) -> ValidationReport:
        context_response: SpecContextResponse = self.context_service.context(spec_ref, force=force)
        editable_files = set(context_response.editable_files)
        coordination_paths = {coordination.path for coordination in context_response.coordination_files}
        substantive_in_scope = any(
            path in editable_files and path not in coordination_paths
            for path in changed_files
        )
        pending_by_path: dict[str, ValidationWarning] = {
            proposal.path: ValidationWarning(path=proposal.path, proposal=proposal)
            for proposal in context_response.pending_proposals
        }
        warning_files: list[ValidationWarning] = []
        note_files: list[ValidationNote] = []
        error_files: list[ValidationError] = []
        for path in changed_files:
            if path == context_response.spec.source_path:
                continue
            if path in coordination_paths:
                if substantive_in_scope:
                    note_files.append(
                        ValidationNote(
                            path=path,
                            message=(
                                "coordination spillover allowed because this change also "
                                "touches a substantive editable file"
                            ),
                        )
                    )
                else:
                    error_files.append(
                        ValidationError(
                            path=path,
                            message=(
                                "coordination files are only allowed alongside a substantive "
                                "editable change"
                            ),
                        )
                    )
                continue
            if path in editable_files:
                continue
            pending = pending_by_path.get(path)
            if pending is not None:
                warning_files.append(pending)
                continue
            owner = self.graph_repository.owner_for_path(path)
            if owner is None:
                error_files.append(
                    ValidationError(
                        path=path,
                        message=(
                            "ungoverned file; record ownership expansion with "
                            f"`sgm propose {context_response.spec.id} {path} \"<reason>\"`"
                        ),
                    )
                )
                continue
            error_files.append(
                ValidationError(
                    path=path,
                    message=(
                        f"owned by {owner[0]}; ask a human, then record "
                        f"`sgm shared allow {owner[0]} {context_response.spec.id} {path} "
                        '"<reason>"`'
                    ),
                )
            )
        if record:
            self.graph_repository.record_validation(
                spec_id=context_response.spec.id,
                target_path=context_response.spec.source_path,
                changed_files=changed_files,
                warning_files=tuple(warning.path for warning in warning_files),
                error_files=tuple(error.path for error in error_files),
            )

        return ValidationReport(
            spec=context_response.spec,
            changed_files=changed_files,
            editable_files=context_response.editable_files,
            coordination_files=tuple(sorted(coordination_paths)),
            warning_files=tuple(warning_files),
            note_files=tuple(note_files),
            error_files=tuple(error_files),
            focus_warning=context_response.focus_warning,
        )
