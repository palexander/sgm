from __future__ import annotations

from dataclasses import dataclass

from sgm.adapters.filesystem import FileSystemAdapter
from sgm.adapters.repository import GraphRepository
from sgm.adapters.system import SystemAdapter
from sgm.application.context_service import ContextService
from sgm.application.init_service import InitService
from sgm.application.refresh_service import RefreshService
from sgm.application.validation_service import ValidationService
from sgm.domain.models import (
    ApprovalResult,
    InitResult,
    PersistResult,
    ProposalListResult,
    ProposalStatus,
    ProposeResult,
    RejectResult,
    RepoContext,
    SpecContextResponse,
    SyncDecisionResult,
    SyncFilesResult,
    SyncSpecResult,
    ValidationSuiteReport,
)
from sgm.domain.paths import to_repo_relative_posix


@dataclass(slots=True)
class SgmService:
    repo_context: RepoContext
    graph_repository: GraphRepository
    filesystem: FileSystemAdapter
    system: SystemAdapter

    def refresh(self) -> None:
        self._refresh_service().refresh()

    def sync_files(self, scan_root: str | None) -> SyncFilesResult:
        return self._refresh_service().sync_files(scan_root)

    def sync_spec(self, yaml_path: str) -> SyncSpecResult:
        return self._refresh_service().sync_spec(yaml_path)

    def sync_decision(self, yaml_path: str) -> SyncDecisionResult:
        return self._refresh_service().sync_decision(yaml_path)

    def context(self, spec_ref: str, force: bool = False) -> SpecContextResponse:
        return self._context_service().context(spec_ref, force=force)

    def validate(
        self,
        spec_ref: str | None,
        record: bool,
        force: bool = False,
    ) -> ValidationSuiteReport:
        return self._validation_service().validate(spec_ref, record, force=force)

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

    def persist(self) -> PersistResult:
        return self.graph_repository.persist()

    def init(self) -> InitResult:
        return InitService(filesystem=self.filesystem).init()

    def _refresh_service(self) -> RefreshService:
        return RefreshService(
            repo_context=self.repo_context,
            graph_repository=self.graph_repository,
            filesystem=self.filesystem,
            system=self.system,
        )

    def _context_service(self) -> ContextService:
        return ContextService(
            repo_context=self.repo_context,
            graph_repository=self.graph_repository,
            system=self.system,
        )

    def _validation_service(self) -> ValidationService:
        return ValidationService(
            repo_context=self.repo_context,
            graph_repository=self.graph_repository,
            system=self.system,
            context_service=self._context_service(),
        )
