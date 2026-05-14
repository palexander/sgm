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
    CoordinationMarkResult,
    CoordinationUnmarkResult,
    ProposalListResult,
    ProposalStatus,
    ProposeResult,
    RejectResult,
    RepoContext,
    SharedAllowResult,
    SharedListResult,
    SharedRevokeResult,
    SpecContextResponse,
    SyncDecisionResult,
    SyncFilesResult,
    SyncSpecResult,
    ValidationSuiteReport,
)
from sgm.domain.paths import to_repo_relative_posix
from sgm.domain.proposal_models import ProposalReviewItem, ProposalReviewResult


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

    def shared_allow(
        self,
        owner_spec_id: str,
        delegate_spec_id: str,
        raw_path: str,
        reason: str,
    ) -> SharedAllowResult:
        path: str = to_repo_relative_posix(self.repo_context.root, raw_path)
        return self.graph_repository.create_delegation(
            owner_spec_id=owner_spec_id,
            delegate_spec_id=delegate_spec_id,
            path=path,
            reason=reason,
        )

    def shared_revoke(
        self,
        owner_spec_id: str,
        delegate_spec_id: str,
        raw_path: str,
    ) -> SharedRevokeResult:
        path: str = to_repo_relative_posix(self.repo_context.root, raw_path)
        return self.graph_repository.revoke_delegation(
            owner_spec_id=owner_spec_id,
            delegate_spec_id=delegate_spec_id,
            path=path,
        )

    def shared_mark_coordination(
        self,
        owner_spec_id: str,
        raw_path: str,
        reason: str,
    ) -> CoordinationMarkResult:
        path: str = to_repo_relative_posix(self.repo_context.root, raw_path)
        return self.graph_repository.mark_coordination(
            owner_spec_id=owner_spec_id,
            path=path,
            reason=reason,
        )

    def shared_unmark_coordination(
        self,
        owner_spec_id: str,
        raw_path: str,
    ) -> CoordinationUnmarkResult:
        path: str = to_repo_relative_posix(self.repo_context.root, raw_path)
        return self.graph_repository.unmark_coordination(
            owner_spec_id=owner_spec_id,
            path=path,
        )

    def shared_list(self, query: str) -> SharedListResult:
        normalized_query = query
        target_path = self.repo_context.root / query
        if target_path.exists():
            normalized_query = to_repo_relative_posix(self.repo_context.root, target_path)
        return self.graph_repository.list_shared(normalized_query)

    def proposals_list(self, status: ProposalStatus | None) -> ProposalListResult:
        return self.graph_repository.list_proposals(status)

    def proposals_review(self) -> ProposalReviewResult:
        review_items: list[ProposalReviewItem] = []
        for proposal in self.graph_repository.list_proposals("pending").proposals:
            context = self.graph_repository.get_context(proposal.spec_id)
            review_items.append(
                ProposalReviewItem(
                    proposal=proposal,
                    spec_title=context.spec.title,
                    spec_text=context.spec.text,
                    governed_files=context.editable_files,
                )
            )
        return ProposalReviewResult(proposals=tuple(review_items))

    def proposals_approve(self, proposal_id: str) -> ApprovalResult:
        return self.graph_repository.approve_proposal(proposal_id)

    def proposals_reject(self, proposal_id: str, review_reason: str | None) -> RejectResult:
        return self.graph_repository.reject_proposal(proposal_id, review_reason)

    def init(self, hooks: str = "none") -> InitResult:
        return InitService(filesystem=self.filesystem).init(hooks=hooks)

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
