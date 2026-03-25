from __future__ import annotations

from dataclasses import dataclass, replace

from sgm.adapters.filesystem import FileSystemAdapter
from sgm.adapters.memgraph import GraphRepository
from sgm.adapters.spec_loader import load_spec_document
from sgm.adapters.system import SystemAdapter
from sgm.domain.errors import EntityNotFoundError, FileNotFoundOnDiskError, NotIndexedError
from sgm.domain.models import (
    ApprovalResult,
    ComplianceSnapshot,
    ContextResponse,
    GoverningSpec,
    ProposalListResult,
    ProposalStatus,
    ProposeResult,
    RejectResult,
    RepoContext,
    SpecDelta,
    SyncFilesResult,
    SyncSpecResult,
    ValidationReport,
    ValidationSummary,
)
from sgm.domain.paths import normalize_scan_root, to_repo_relative_posix
from sgm.domain.scoring import merge_compliance
from sgm.domain.spec_deltas import build_spec_delta
from sgm.domain.validation import validate_assertions


@dataclass(slots=True)
class SgmService:
    repo_context: RepoContext
    graph_repository: GraphRepository
    filesystem: FileSystemAdapter
    system: SystemAdapter

    def refresh(self) -> None:
        self.graph_repository.sync_files(".", self.filesystem.scan("."))
        spec_paths: tuple[str, ...] = self.filesystem.list_spec_files()
        for spec_path in spec_paths:
            spec = load_spec_document(
                self.repo_context.root / spec_path,
                self.repo_context.root,
            )
            self.graph_repository.sync_spec(spec)
        self.graph_repository.prune_specs(spec_paths)

    def sync_files(self, scan_root: str | None) -> SyncFilesResult:
        normalized_root: str = normalize_scan_root(self.repo_context.root, scan_root)
        nodes = self.filesystem.scan(normalized_root)
        return self.graph_repository.sync_files(normalized_root, nodes)

    def sync_spec(self, yaml_path: str) -> SyncSpecResult:
        normalized_path: str = to_repo_relative_posix(self.repo_context.root, yaml_path)
        spec = load_spec_document(
            self.repo_context.root / normalized_path,
            self.repo_context.root,
        )
        return self.graph_repository.sync_spec(spec)

    def context(self, raw_target_path: str) -> ContextResponse:
        target_path: str = to_repo_relative_posix(self.repo_context.root, raw_target_path)
        response: ContextResponse = self.graph_repository.get_context(target_path)
        return ContextResponse(
            target_path=response.target_path,
            specs=self._with_spec_deltas(response.specs),
            siblings=response.siblings,
            indexed=response.indexed,
        )

    def validate(
        self,
        raw_target_path: str,
        record: bool,
    ) -> tuple[ValidationReport, dict[str, float], dict[str, tuple[float, int, int]]]:
        target_path: str = to_repo_relative_posix(self.repo_context.root, raw_target_path)
        try:
            file_content: str = self.filesystem.read_text(target_path)
        except FileNotFoundOnDiskError:
            raise

        context_response: ContextResponse = self.graph_repository.get_context(target_path)
        if not context_response.indexed:
            raise NotIndexedError("target file missing from graph")
        if not context_response.specs:
            return ValidationReport(spec_summaries=()), {}, {}

        try:
            assertions_by_spec = self.graph_repository.get_assertions_for_path(target_path)
        except EntityNotFoundError as error:
            raise NotIndexedError(str(error)) from error

        previous = self.graph_repository.get_existing_scores(target_path)
        governing_specs: tuple[GoverningSpec, ...] = self._with_spec_deltas(
            context_response.specs
        )
        summaries: list[ValidationSummary] = []
        updated: dict[str, tuple[float, int, int]] = {}
        for spec in governing_specs:
            spec_id: str = spec.id
            assertions = assertions_by_spec.get(spec_id, ())
            summary = validate_assertions(
                path=target_path,
                file_content=file_content,
                assertions=assertions,
            )
            summary = ValidationSummary(
                spec_id=spec_id,
                results=summary.results,
                total_checks=summary.total_checks,
                passed_checks=summary.passed_checks,
                failed_errors=summary.failed_errors,
                failed_warnings=summary.failed_warnings,
                inconclusive_warnings=summary.inconclusive_warnings,
            )
            summaries.append(summary)
            if record:
                existing_snapshot: ComplianceSnapshot = previous.get(
                    spec_id,
                    ComplianceSnapshot(
                        total_checks=0,
                        passed_checks=0,
                        failed_errors=0,
                        failed_warnings=0,
                        score=1.0,
                    ),
                )
                merged_snapshot: ComplianceSnapshot = merge_compliance(
                    previous=existing_snapshot,
                    total_checks=summary.total_checks,
                    passed_checks=summary.passed_checks,
                    failed_errors=summary.failed_errors,
                    failed_warnings=summary.failed_warnings,
                )
                persisted_snapshot: ComplianceSnapshot = (
                    self.graph_repository.apply_compliance_update(
                        spec_id=spec_id,
                        target_path=target_path,
                        snapshot=merged_snapshot,
                    )
                )
                updated[spec_id] = (
                    persisted_snapshot.score,
                    persisted_snapshot.passed_checks,
                    persisted_snapshot.total_checks,
                )
        previous_scores: dict[str, float] = {
            spec_id: snapshot.score for spec_id, snapshot in previous.items()
        }
        spec_deltas: tuple[SpecDelta, ...] = tuple(
            spec.spec_delta for spec in governing_specs if spec.spec_delta is not None
        )
        return (
            ValidationReport(spec_summaries=tuple(summaries), spec_deltas=spec_deltas),
            previous_scores,
            updated,
        )

    def propose(self, spec_id: str, raw_path: str, reason: str) -> ProposeResult:
        path: str = to_repo_relative_posix(self.repo_context.root, raw_path)
        return self.graph_repository.create_proposal(
            proposal_id=self.system.new_proposal_id(),
            spec_id=spec_id,
            path=path,
            reason=reason,
        )

    def proposals_list(self, status: ProposalStatus | None) -> ProposalListResult:
        return self.graph_repository.list_proposals(status)

    def proposals_approve(self, proposal_id: str) -> ApprovalResult:
        return self.graph_repository.approve_proposal(proposal_id)

    def proposals_reject(self, proposal_id: str, review_reason: str | None) -> RejectResult:
        return self.graph_repository.reject_proposal(proposal_id, review_reason)

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
