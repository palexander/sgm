from __future__ import annotations

from dataclasses import dataclass

from sgm.adapters.repository import GraphRepository
from sgm.adapters.system import SystemAdapter
from sgm.application.context_service import ContextService
from sgm.domain.models import (
    RepoContext,
    SpecContextResponse,
    ValidationReport,
    ValidationSuiteReport,
    ValidationWarning,
)
from sgm.domain.selectors import matches_selector


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
            )
            for current_spec_ref in spec_refs
        )
        return ValidationSuiteReport(reports=reports)

    def _validate_spec(
        self,
        spec_ref: str,
        changed_files: tuple[str, ...],
        record: bool,
    ) -> ValidationReport:
        context_response: SpecContextResponse = self.context_service.context(spec_ref)
        allowed_files: set[str] = set(context_response.governed_files)
        allowed_files.add(context_response.spec.source_path)
        pending_by_path: dict[str, ValidationWarning] = {
            proposal.path: ValidationWarning(path=proposal.path, proposal=proposal)
            for proposal in context_response.pending_proposals
        }
        warning_files: list[ValidationWarning] = []
        error_files: list[str] = []
        for path in changed_files:
            if path in allowed_files or any(
                matches_selector(path=path, selector=selector)
                for selector in context_response.spec.selectors
            ):
                continue
            pending = pending_by_path.get(path)
            if pending is not None:
                warning_files.append(pending)
            else:
                error_files.append(path)
        if record:
            self.graph_repository.record_validation(
                spec_id=context_response.spec.id,
                target_path=context_response.spec.source_path,
                changed_files=changed_files,
                warning_files=tuple(warning.path for warning in warning_files),
                error_files=tuple(error_files),
            )

        return ValidationReport(
            spec=context_response.spec,
            changed_files=changed_files,
            governed_files=context_response.governed_files,
            warning_files=tuple(warning_files),
            error_files=tuple(error_files),
        )
