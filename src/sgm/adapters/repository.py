from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import uuid4

try:
    import fcntl
except ImportError:  # pragma: no cover - advisory locking is unavailable on Windows.
    fcntl = None

from sgm.domain.errors import EntityNotFoundError, InfrastructureError, SpecValidationError
from sgm.domain.models import (
    ApprovalResult,
    CodeNode,
    Coordination,
    CoordinationMarkResult,
    CoordinationUnmarkResult,
    DecisionDocument,
    DecisionStatus,
    Delegation,
    GoverningSpec,
    Proposal,
    ProposalListResult,
    ProposalStatus,
    ProposeResult,
    ReadRequirement,
    RejectResult,
    RelatedDecision,
    SharedAllowResult,
    SharedListResult,
    SharedRevokeResult,
    SpecContextResponse,
    SpecDocument,
    SyncDecisionResult,
    SyncFilesResult,
    SyncSpecResult,
)
from sgm.domain.selectors import matches_selector


class GraphRepository(Protocol):
    def reset(self) -> None: ...
    def sync_files(self, scan_root: str, nodes: tuple[CodeNode, ...]) -> SyncFilesResult: ...
    def sync_spec(self, spec: SpecDocument) -> SyncSpecResult: ...
    def sync_decision(self, decision: DecisionDocument) -> SyncDecisionResult: ...
    def prune_specs(self, source_paths: tuple[str, ...]) -> None: ...
    def prune_decisions(self, source_paths: tuple[str, ...]) -> None: ...
    def list_active_specs(self) -> tuple[str, ...]: ...
    def assert_unique_active_ownership(self) -> None: ...
    def get_context(self, spec_ref: str) -> SpecContextResponse: ...
    def owner_for_path(self, path: str) -> tuple[str, str, str] | None: ...
    def record_validation(
        self,
        spec_id: str,
        target_path: str,
        changed_files: tuple[str, ...],
        warning_files: tuple[str, ...],
        error_files: tuple[str, ...],
    ) -> None: ...
    def create_proposal(
        self,
        proposal_id: str,
        spec_id: str,
        path: str,
        reason: str,
    ) -> ProposeResult: ...
    def create_delegation(
        self,
        owner_spec_id: str,
        delegate_spec_id: str,
        path: str,
        reason: str,
    ) -> SharedAllowResult: ...
    def revoke_delegation(
        self,
        owner_spec_id: str,
        delegate_spec_id: str,
        path: str,
    ) -> SharedRevokeResult: ...
    def mark_coordination(
        self,
        owner_spec_id: str,
        path: str,
        reason: str,
    ) -> CoordinationMarkResult: ...
    def unmark_coordination(
        self,
        owner_spec_id: str,
        path: str,
    ) -> CoordinationUnmarkResult: ...
    def list_shared(self, query: str) -> SharedListResult: ...
    def list_proposals(self, status: ProposalStatus | None) -> ProposalListResult: ...
    def approve_proposal(self, proposal_id: str) -> ApprovalResult: ...
    def reject_proposal(self, proposal_id: str, review_reason: str | None) -> RejectResult: ...


@dataclass(slots=True)
class FileRepository:
    repo_root: Path
    work_root: Path = field(init=False)
    state_path: Path = field(init=False)
    work_proposals_root: Path = field(init=False)
    work_validations_root: Path = field(init=False)
    persisted_root: Path = field(init=False)
    persisted_proposals_root: Path = field(init=False)
    persisted_delegations_root: Path = field(init=False)
    persisted_coordination_root: Path = field(init=False)

    def __post_init__(self) -> None:
        self.work_root = self.repo_root / ".sgm" / "work"
        self.state_path = self.work_root / "state.json"
        self.work_proposals_root = self.work_root / "proposals"
        self.work_validations_root = self.work_root / "validations"
        self.persisted_root = self.repo_root / ".sgm" / "persisted"
        self.persisted_proposals_root = self.persisted_root / "proposals"
        self.persisted_delegations_root = self.persisted_root / "delegations"
        self.persisted_coordination_root = self.persisted_root / "coordination"

    def reset(self) -> None:
        self._write_state(_empty_state())
        self._clear_directory(self.work_proposals_root)
        self._clear_directory(self.work_validations_root)

    def sync_files(self, scan_root: str, nodes: tuple[CodeNode, ...]) -> SyncFilesResult:
        state = self._load_state()
        prefix: str = "" if scan_root == "." else f"{scan_root.rstrip('/')}/"
        existing_paths: set[str] = {
            path for path in state["code_nodes"] if path == scan_root or path.startswith(prefix)
        }
        current_paths: set[str] = {node.path for node in nodes}
        stale_paths: set[str] = existing_paths - current_paths

        for node in nodes:
            state["code_nodes"][node.path] = {
                "id": node.id,
                "path": node.path,
                "kind": node.kind,
                "name": node.name,
                "last_modified": node.last_modified.isoformat(timespec="seconds"),
            }
        for stale_path in stale_paths:
            state["code_nodes"].pop(stale_path, None)
            for spec_data in state["specs"].values():
                spec_data["governs"].pop(stale_path, None)
            for decision_data in state["decisions"].values():
                decision_data["informs"] = [
                    path for path in decision_data["informs"] if path != stale_path
                ]

        self._write_state(state)
        return SyncFilesResult(root=scan_root, scanned_paths=len(nodes))

    def sync_spec(self, spec: SpecDocument) -> SyncSpecResult:
        state = self._load_state()
        existing_spec = cast(dict[str, Any] | None, state["specs"].get(spec.id))
        previous_source_text: str | None = None
        has_local_snapshot_history = existing_spec is not None
        if existing_spec is not None:
            existing_source_text = cast(str, existing_spec["source_text"])
            if existing_source_text != spec.source_text:
                previous_source_text = existing_source_text

        matched_paths: dict[str, int] = {}
        for selector in spec.governs:
            for path, code_node in state["code_nodes"].items():
                if code_node["kind"] != "file":
                    continue
                if matches_selector(path=path, selector=selector.selector):
                    existing_priority = matched_paths.get(path)
                    if existing_priority is None or selector.priority < existing_priority:
                        matched_paths[path] = selector.priority

        governs: dict[str, dict[str, Any]]
        if existing_spec is None:
            governs = {}
        else:
            governs = cast(dict[str, dict[str, Any]], existing_spec["governs"])

        for path, edge_data in list(governs.items()):
            if edge_data["selector"] is not None and path not in matched_paths:
                governs.pop(path, None)

        for path, priority in matched_paths.items():
            selector_value = next(
                selector.selector
                for selector in spec.governs
                if selector.priority == priority
                and matches_selector(path=path, selector=selector.selector)
            )
            governs[path] = {"priority": priority, "selector": selector_value}

        state["specs"][spec.id] = {
            "id": spec.id,
            "source_path": spec.source_path,
            "source_text": spec.source_text,
            "previous_source_text": previous_source_text,
            "has_local_snapshot_history": has_local_snapshot_history,
            "title": spec.title,
            "text": spec.text,
            "status": spec.status,
            "author": spec.author,
            "governs": governs,
        }
        self._write_state(state)
        return SyncSpecResult(
            spec_id=spec.id,
            governed_count=len(matched_paths),
            selectors=tuple(selector.selector for selector in spec.governs),
        )

    def sync_decision(self, decision: DecisionDocument) -> SyncDecisionResult:
        state = self._load_state()
        matched_paths: set[str] = set()
        for touch in decision.touches:
            for path, code_node in state["code_nodes"].items():
                if code_node["kind"] != "file":
                    continue
                if matches_selector(path=path, selector=touch.selector):
                    matched_paths.add(path)

        state["decisions"][decision.id] = {
            "id": decision.id,
            "source_path": decision.source_path,
            "source_text": decision.source_text,
            "title": decision.title,
            "status": decision.status,
            "context": decision.context,
            "decision": decision.decision,
            "consequences": decision.consequences,
            "touches": [touch.selector for touch in decision.touches],
            "informs": sorted(matched_paths),
        }
        self._write_state(state)
        return SyncDecisionResult(
            decision_id=decision.id,
            informed_count=len(matched_paths),
            selectors=tuple(touch.selector for touch in decision.touches),
        )

    def prune_specs(self, source_paths: tuple[str, ...]) -> None:
        state = self._load_state()
        active_paths = set(source_paths)
        for spec_id in list(state["specs"].keys()):
            source_path = cast(str | None, state["specs"][spec_id].get("source_path"))
            if source_path is None or source_path not in active_paths:
                state["specs"].pop(spec_id, None)
        self._write_state(state)

    def prune_decisions(self, source_paths: tuple[str, ...]) -> None:
        state = self._load_state()
        active_paths = set(source_paths)
        for decision_id in list(state["decisions"].keys()):
            source_path = cast(str | None, state["decisions"][decision_id].get("source_path"))
            if source_path is None or source_path not in active_paths:
                state["decisions"].pop(decision_id, None)
        self._write_state(state)

    def list_active_specs(self) -> tuple[str, ...]:
        state = self._load_state()
        active_specs = [
            cast(str, spec_data["source_path"])
            for spec_data in cast(dict[str, dict[str, Any]], state["specs"]).values()
            if cast(str, spec_data["status"]) == "active"
        ]
        return tuple(sorted(active_specs))

    def assert_unique_active_ownership(self) -> None:
        self._ownership_index(self._load_state())

    def owner_for_path(self, path: str) -> tuple[str, str, str] | None:
        state = self._load_state()
        owner = self._ownership_index(state).get(path)
        if owner is None:
            return None
        spec_id, spec_data = owner
        return (
            spec_id,
            cast(str, spec_data["source_path"]),
            cast(str, spec_data["title"]),
        )

    def get_context(self, spec_ref: str) -> SpecContextResponse:
        state = self._load_state()
        ownership_index = self._ownership_index(state)
        spec_id, spec_data = self._resolve_spec_ref(state, spec_ref)
        spec = self._build_governing_spec(spec_id, spec_data)
        owned_paths = self._owned_paths_for_spec(spec_id=spec_id, state=state)
        delegated_files = tuple(
            delegation
            for delegation in self._active_delegations(state, ownership_index)
            if delegation.delegate_spec_id == spec_id
        )
        editable_paths: set[str] = set(owned_paths)
        editable_paths.update(delegation.path for delegation in delegated_files)
        coordination_files = tuple(
            coordination
            for coordination in self._active_coordination(state, ownership_index)
            if coordination.owner_spec_id != spec_id
        )

        read_specs: list[ReadRequirement] = [ReadRequirement(spec=spec, role="target", paths=())]
        owner_paths: dict[str, list[str]] = {}
        for delegation in delegated_files:
            owner_paths.setdefault(delegation.owner_spec_id, []).append(delegation.path)
        for owner_spec_id in sorted(owner_paths):
            owner_spec_data = cast(dict[str, Any], state["specs"][owner_spec_id])
            read_specs.append(
                ReadRequirement(
                    spec=self._build_governing_spec(owner_spec_id, owner_spec_data),
                    role="owner",
                    paths=tuple(sorted(owner_paths[owner_spec_id])),
                )
            )

        decisions: list[RelatedDecision] = []
        decision_scope = editable_paths.union(
            coordination.path for coordination in coordination_files
        )
        for decision_id, decision_data in state["decisions"].items():
            if decision_data["status"] != "active":
                continue
            decision_paths = set(cast(list[str], decision_data["informs"]))
            if decision_paths.isdisjoint(decision_scope):
                continue
            decisions.append(
                RelatedDecision(
                    id=decision_id,
                    title=cast(str, decision_data["title"]),
                    status=cast(DecisionStatus, decision_data["status"]),
                    context=cast(str, decision_data["context"]),
                    decision=cast(str, decision_data["decision"]),
                    consequences=cast(str, decision_data["consequences"]),
                )
            )
        decisions.sort(key=lambda decision: decision.id)
        pending_proposals = tuple(
            proposal
            for proposal in self.list_proposals("pending").proposals
            if proposal.spec_id == spec_id
        )
        next_steps = (
            f'Unowned files: `sgm propose {spec_id} <path> "<reason>"`.',
            (
                "Files owned by another spec: ask a human, then record "
                f'`sgm shared allow <owner-spec-id> {spec_id} <path> "<reason>"`.'
            ),
            "Coordination files are only for follow-through alongside substantive in-scope work.",
            f"After edits: `sgm validate {spec.source_path}`.",
        )

        return SpecContextResponse(
            spec=spec,
            read_specs=tuple(read_specs),
            decisions=tuple(decisions),
            editable_files=tuple(sorted(editable_paths)),
            delegated_files=delegated_files,
            coordination_files=coordination_files,
            pending_proposals=pending_proposals,
            next_steps=next_steps,
        )

    def record_validation(
        self,
        spec_id: str,
        target_path: str,
        changed_files: tuple[str, ...],
        warning_files: tuple[str, ...],
        error_files: tuple[str, ...],
    ) -> None:
        state = self._load_state()
        spec_data = cast(dict[str, Any] | None, state["specs"].get(spec_id))
        if spec_data is None:
            raise EntityNotFoundError(f"spec not found: {spec_id}")
        record_path = (
            self.work_validations_root
            / spec_id
            / (f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}.json")
        )
        payload = {
            "spec_id": spec_id,
            "path": target_path,
            "source_path": cast(str, spec_data["source_path"]),
            "changed_files": list(changed_files),
            "warning_files": list(warning_files),
            "error_files": list(error_files),
            "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        self._write_json_file(record_path, payload)

    def create_proposal(
        self,
        proposal_id: str,
        spec_id: str,
        path: str,
        reason: str,
    ) -> ProposeResult:
        with self._proposal_target_lock(spec_id=spec_id, path=path):
            state = self._load_state()
            spec_data = cast(dict[str, Any] | None, state["specs"].get(spec_id))
            if spec_data is None:
                raise EntityNotFoundError(f"spec not found: {spec_id}")
            if path not in state["code_nodes"]:
                raise EntityNotFoundError(f"file not indexed: {path}")
            owner = self._ownership_index(state).get(path)
            if owner is not None and owner[0] != spec_id:
                return ProposeResult(
                    created=False,
                    proposal_id=None,
                    spec_id=spec_id,
                    spec_title=cast(str, spec_data["title"]),
                    path=path,
                    reason=reason,
                    owner_spec_id=owner[0],
                    owner_spec_title=cast(str, owner[1]["title"]),
                )
            governs = cast(dict[str, Any], spec_data["governs"])
            if path in governs or path in self._approved_paths_by_spec().get(spec_id, set()):
                return ProposeResult(
                    created=False,
                    proposal_id=None,
                    spec_id=spec_id,
                    spec_title=cast(str, spec_data["title"]),
                    path=path,
                    reason=reason,
                )

            pending_proposal_id = self._pending_proposal_id(spec_id=spec_id, path=path)
            if pending_proposal_id is not None:
                return ProposeResult(
                    created=False,
                    proposal_id=pending_proposal_id,
                    spec_id=spec_id,
                    spec_title=cast(str, spec_data["title"]),
                    path=path,
                    reason=reason,
                )

            payload = {
                "id": proposal_id,
                "spec_id": spec_id,
                "path": path,
                "reason": reason,
                "status": "pending",
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "reviewed_at": None,
                "review_reason": None,
            }
            self._write_json_file(self.persisted_proposals_root / f"{proposal_id}.json", payload)
            return ProposeResult(
                created=True,
                proposal_id=proposal_id,
                spec_id=spec_id,
                spec_title=cast(str, spec_data["title"]),
                path=path,
                reason=reason,
            )

    def list_proposals(self, status: ProposalStatus | None) -> ProposalListResult:
        rows = list(self._load_proposal_rows().values())
        if status is not None:
            rows = [row for row in rows if row["status"] == status]
        rows.sort(key=lambda row: (cast(str, row["created_at"]), cast(str, row["id"])))
        proposals = tuple(self._proposal_from_state(row) for row in rows)
        return ProposalListResult(proposals=proposals, status_filter=status)

    def approve_proposal(self, proposal_id: str) -> ApprovalResult:
        proposal_path, proposal = self._proposal_record(proposal_id)
        if proposal["status"] != "pending":
            raise EntityNotFoundError(f"pending proposal not found: {proposal_id}")
        spec_id = cast(str, proposal["spec_id"])
        path = cast(str, proposal["path"])
        state = self._load_state()
        if spec_id not in state["specs"]:
            raise EntityNotFoundError(f"spec not found: {spec_id}")
        proposal["status"] = "approved"
        proposal["reviewed_at"] = datetime.now().isoformat(timespec="seconds")
        persisted_path = self.persisted_proposals_root / f"{proposal_id}.json"
        self._write_json_file(persisted_path, proposal)
        if proposal_path != persisted_path and proposal_path.exists():
            proposal_path.unlink()
        return ApprovalResult(proposal_id=proposal_id, spec_id=spec_id, path=path)

    def reject_proposal(self, proposal_id: str, review_reason: str | None) -> RejectResult:
        proposal_path, proposal = self._proposal_record(proposal_id)
        if proposal["status"] != "pending":
            raise EntityNotFoundError(f"pending proposal not found: {proposal_id}")
        proposal["status"] = "rejected"
        proposal["reviewed_at"] = datetime.now().isoformat(timespec="seconds")
        proposal["review_reason"] = review_reason
        persisted_path = self.persisted_proposals_root / f"{proposal_id}.json"
        self._write_json_file(persisted_path, proposal)
        if proposal_path != persisted_path and proposal_path.exists():
            proposal_path.unlink()
        return RejectResult(proposal_id=proposal_id, review_reason=review_reason)

    def create_delegation(
        self,
        owner_spec_id: str,
        delegate_spec_id: str,
        path: str,
        reason: str,
    ) -> SharedAllowResult:
        state = self._load_state()
        ownership_index = self._ownership_index(state)
        self._assert_active_owned_path(
            state=state,
            ownership_index=ownership_index,
            owner_spec_id=owner_spec_id,
            path=path,
        )
        self._assert_active_spec(state, delegate_spec_id)
        if owner_spec_id == delegate_spec_id:
            raise SpecValidationError("owner and delegate must be different specs")

        record_id = self._delegation_record_id(owner_spec_id, delegate_spec_id, path)
        record_path = self.persisted_delegations_root / f"{record_id}.json"
        existing = self._load_optional_json_file(record_path)
        if existing is not None and cast(str, existing.get("status")) == "active":
            return SharedAllowResult(
                created=False,
                delegation=self._delegation_from_state(existing),
            )

        now = datetime.now(UTC).isoformat(timespec="seconds")
        payload = {
            "id": record_id,
            "owner_spec_id": owner_spec_id,
            "delegate_spec_id": delegate_spec_id,
            "path": path,
            "reason": reason,
            "status": "active",
            "created_at": cast(str | None, existing.get("created_at")) if existing else now,
            "revoked_at": None,
        }
        self._write_json_file(record_path, payload)
        return SharedAllowResult(
            created=True,
            delegation=self._delegation_from_state(payload),
        )

    def revoke_delegation(
        self,
        owner_spec_id: str,
        delegate_spec_id: str,
        path: str,
    ) -> SharedRevokeResult:
        record_id = self._delegation_record_id(owner_spec_id, delegate_spec_id, path)
        record_path = self.persisted_delegations_root / f"{record_id}.json"
        existing = self._load_optional_json_file(record_path)
        if existing is None:
            return SharedRevokeResult(
                revoked=False,
                delegation=Delegation(
                    id=record_id,
                    owner_spec_id=owner_spec_id,
                    delegate_spec_id=delegate_spec_id,
                    path=path,
                    reason="",
                    status="revoked",
                    created_at=datetime.now(UTC),
                    revoked_at=datetime.now(UTC),
                ),
            )
        if cast(str, existing.get("status")) != "active":
            return SharedRevokeResult(
                revoked=False,
                delegation=self._delegation_from_state(existing),
            )
        existing["status"] = "revoked"
        existing["revoked_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        self._write_json_file(record_path, existing)
        return SharedRevokeResult(
            revoked=True,
            delegation=self._delegation_from_state(existing),
        )

    def mark_coordination(
        self,
        owner_spec_id: str,
        path: str,
        reason: str,
    ) -> CoordinationMarkResult:
        state = self._load_state()
        ownership_index = self._ownership_index(state)
        self._assert_active_owned_path(
            state=state,
            ownership_index=ownership_index,
            owner_spec_id=owner_spec_id,
            path=path,
        )

        record_id = self._coordination_record_id(owner_spec_id, path)
        record_path = self.persisted_coordination_root / f"{record_id}.json"
        existing = self._load_optional_json_file(record_path)
        if existing is not None and cast(str, existing.get("status")) == "active":
            return CoordinationMarkResult(
                created=False,
                coordination=self._coordination_from_state(existing),
            )

        now = datetime.now(UTC).isoformat(timespec="seconds")
        payload = {
            "id": record_id,
            "owner_spec_id": owner_spec_id,
            "path": path,
            "reason": reason,
            "status": "active",
            "created_at": cast(str | None, existing.get("created_at")) if existing else now,
            "revoked_at": None,
        }
        self._write_json_file(record_path, payload)
        return CoordinationMarkResult(
            created=True,
            coordination=self._coordination_from_state(payload),
        )

    def unmark_coordination(
        self,
        owner_spec_id: str,
        path: str,
    ) -> CoordinationUnmarkResult:
        record_id = self._coordination_record_id(owner_spec_id, path)
        record_path = self.persisted_coordination_root / f"{record_id}.json"
        existing = self._load_optional_json_file(record_path)
        if existing is None:
            return CoordinationUnmarkResult(
                revoked=False,
                coordination=Coordination(
                    id=record_id,
                    owner_spec_id=owner_spec_id,
                    path=path,
                    reason="",
                    status="revoked",
                    created_at=datetime.now(UTC),
                    revoked_at=datetime.now(UTC),
                ),
            )
        if cast(str, existing.get("status")) != "active":
            return CoordinationUnmarkResult(
                revoked=False,
                coordination=self._coordination_from_state(existing),
            )
        existing["status"] = "revoked"
        existing["revoked_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        self._write_json_file(record_path, existing)
        return CoordinationUnmarkResult(
            revoked=True,
            coordination=self._coordination_from_state(existing),
        )

    def list_shared(self, query: str) -> SharedListResult:
        state = self._load_state()
        ownership_index = self._ownership_index(state)
        delegations = self._active_delegations(state, ownership_index)
        coordination = self._active_coordination(state, ownership_index)

        try:
            spec_id, spec_data = self._resolve_spec_ref(state, query)
        except EntityNotFoundError:
            spec_id = None
            spec_data = None
        if spec_id is not None and spec_data is not None:
            return SharedListResult(
                query=query,
                spec_id=spec_id,
                spec_title=cast(str, spec_data["title"]),
                path=None,
                owner_spec_id=None,
                owner_spec_title=None,
                owned_delegations=tuple(
                    delegation for delegation in delegations if delegation.owner_spec_id == spec_id
                ),
                delegated_to_spec=tuple(
                    delegation
                    for delegation in delegations
                    if delegation.delegate_spec_id == spec_id
                ),
                owned_coordination=tuple(
                    item for item in coordination if item.owner_spec_id == spec_id
                ),
                available_coordination=tuple(
                    item for item in coordination if item.owner_spec_id != spec_id
                ),
                path_delegations=(),
                path_coordination=None,
            )

        if query not in state["code_nodes"]:
            raise EntityNotFoundError(f"path or spec not found: {query}")
        owner = ownership_index.get(query)
        owner_spec_id: str | None = None
        owner_spec_title: str | None = None
        if owner is not None:
            owner_spec_id, owner_data = owner
            owner_spec_title = cast(str, owner_data["title"])
        return SharedListResult(
            query=query,
            spec_id=None,
            spec_title=None,
            path=query,
            owner_spec_id=owner_spec_id,
            owner_spec_title=owner_spec_title,
            owned_delegations=(),
            delegated_to_spec=(),
            owned_coordination=(),
            available_coordination=(),
            path_delegations=tuple(
                delegation for delegation in delegations if delegation.path == query
            ),
            path_coordination=next(
                (item for item in coordination if item.path == query),
                None,
            ),
        )

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return _empty_state()
        try:
            raw_state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise InfrastructureError(f"failed to read state: {error}") from error
        if not isinstance(raw_state, dict):
            raise InfrastructureError("state file must contain a mapping")
        return {
            "code_nodes": cast(dict[str, Any], raw_state.get("code_nodes", {})),
            "specs": cast(dict[str, Any], raw_state.get("specs", {})),
            "decisions": cast(dict[str, Any], raw_state.get("decisions", {})),
        }

    def _write_state(self, state: dict[str, Any]) -> None:
        self._write_json_file(self.state_path, state)

    def _write_json_file(self, path: Path, payload: dict[str, Any]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
            tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            tmp_path.replace(path)
        except OSError as error:
            raise InfrastructureError(f"failed to write state: {error}") from error

    def _proposal_from_state(self, proposal_data: dict[str, Any]) -> Proposal:
        reviewed_at = cast(str | None, proposal_data["reviewed_at"])
        return Proposal(
            id=cast(str, proposal_data["id"]),
            spec_id=cast(str, proposal_data["spec_id"]),
            path=cast(str, proposal_data["path"]),
            reason=cast(str, proposal_data["reason"]),
            status=cast(ProposalStatus, proposal_data["status"]),
            created_at=datetime.fromisoformat(cast(str, proposal_data["created_at"])),
            reviewed_at=datetime.fromisoformat(reviewed_at) if reviewed_at is not None else None,
            review_reason=cast(str | None, proposal_data["review_reason"]),
        )

    def _load_proposal_rows(self) -> dict[str, dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for root in (self.persisted_proposals_root, self.work_proposals_root):
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*.json")):
                payload = self._load_json_file(path)
                rows[cast(str, payload["id"])] = payload
        return rows

    def _proposal_record(self, proposal_id: str) -> tuple[Path, dict[str, Any]]:
        for root in (self.work_proposals_root, self.persisted_proposals_root):
            path = root / f"{proposal_id}.json"
            if path.is_file():
                return path, self._load_json_file(path)
        raise EntityNotFoundError(f"pending proposal not found: {proposal_id}")

    def _approved_paths_by_spec(self) -> dict[str, set[str]]:
        approved: dict[str, set[str]] = {}
        for proposal in self._load_proposal_rows().values():
            if proposal["status"] != "approved":
                continue
            spec_id = cast(str, proposal["spec_id"])
            approved.setdefault(spec_id, set()).add(cast(str, proposal["path"]))
        return approved

    def _pending_proposal_id(self, spec_id: str, path: str) -> str | None:
        for proposal in self._load_proposal_rows().values():
            if proposal["status"] != "pending":
                continue
            if proposal["spec_id"] != spec_id or proposal["path"] != path:
                continue
            return cast(str, proposal["id"])
        return None

    @contextmanager
    def _proposal_target_lock(self, spec_id: str, path: str):
        digest = hashlib.sha256(f"{spec_id}\0{path}".encode()).hexdigest()
        lock_path = self.work_root / "locks" / "proposals" / f"{digest}.lock"
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with lock_path.open("a+", encoding="utf-8") as lock_file:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    if fcntl is not None:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except OSError as error:
            raise InfrastructureError(f"failed to acquire proposal lock: {error}") from error

    def _default_priority(self, governs: dict[str, Any]) -> int:
        priorities = [int(edge["priority"]) for edge in governs.values()]
        return min(priorities) if priorities else 1

    def _resolve_spec_ref(
        self,
        state: dict[str, Any],
        spec_ref: str,
    ) -> tuple[str, dict[str, Any]]:
        specs = cast(dict[str, dict[str, Any]], state["specs"])
        direct = specs.get(spec_ref)
        if direct is not None:
            return spec_ref, direct

        source_matches = [
            (spec_id, spec_data)
            for spec_id, spec_data in specs.items()
            if cast(str, spec_data["source_path"]) == spec_ref
        ]
        if len(source_matches) == 1:
            return source_matches[0]

        basename_matches = [
            (spec_id, spec_data)
            for spec_id, spec_data in specs.items()
            if Path(cast(str, spec_data["source_path"])).name == spec_ref
        ]
        if len(basename_matches) == 1:
            return basename_matches[0]
        if len(basename_matches) > 1:
            raise EntityNotFoundError(f"ambiguous spec reference: {spec_ref}")
        raise EntityNotFoundError(f"spec not found: {spec_ref}")

    def _load_json_file(self, path: Path) -> dict[str, Any]:
        try:
            raw_payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise InfrastructureError(f"failed to read state: {error}") from error
        if not isinstance(raw_payload, dict):
            raise InfrastructureError("state file must contain a mapping")
        return cast(dict[str, Any], raw_payload)

    def _load_optional_json_file(self, path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        return self._load_json_file(path)

    def _shared_rows(self, root: Path) -> tuple[dict[str, Any], ...]:
        if not root.is_dir():
            return ()
        rows: list[dict[str, Any]] = []
        for path in sorted(root.rglob("*.json")):
            rows.append(self._load_json_file(path))
        return tuple(rows)

    def _delegation_record_id(self, owner_spec_id: str, delegate_spec_id: str, path: str) -> str:
        digest = hashlib.sha256(f"{owner_spec_id}\0{delegate_spec_id}\0{path}".encode()).hexdigest()
        return f"delegation-{digest[:16]}"

    def _coordination_record_id(self, owner_spec_id: str, path: str) -> str:
        digest = hashlib.sha256(f"{owner_spec_id}\0{path}".encode()).hexdigest()
        return f"coordination-{digest[:16]}"

    def _delegation_from_state(self, payload: dict[str, Any]) -> Delegation:
        revoked_at = cast(str | None, payload.get("revoked_at"))
        return Delegation(
            id=cast(str, payload["id"]),
            owner_spec_id=cast(str, payload["owner_spec_id"]),
            delegate_spec_id=cast(str, payload["delegate_spec_id"]),
            path=cast(str, payload["path"]),
            reason=cast(str, payload["reason"]),
            status=cast(str, payload["status"]),
            created_at=datetime.fromisoformat(cast(str, payload["created_at"])),
            revoked_at=datetime.fromisoformat(revoked_at) if revoked_at else None,
        )

    def _coordination_from_state(self, payload: dict[str, Any]) -> Coordination:
        revoked_at = cast(str | None, payload.get("revoked_at"))
        return Coordination(
            id=cast(str, payload["id"]),
            owner_spec_id=cast(str, payload["owner_spec_id"]),
            path=cast(str, payload["path"]),
            reason=cast(str, payload["reason"]),
            status=cast(str, payload["status"]),
            created_at=datetime.fromisoformat(cast(str, payload["created_at"])),
            revoked_at=datetime.fromisoformat(revoked_at) if revoked_at else None,
        )

    def _active_delegations(
        self,
        state: dict[str, Any],
        ownership_index: dict[str, tuple[str, dict[str, Any]]],
    ) -> tuple[Delegation, ...]:
        active_specs = self._active_specs(state)
        delegations: list[Delegation] = []
        for row in self._shared_rows(self.persisted_delegations_root):
            if cast(str, row.get("status")) != "active":
                continue
            delegation = self._delegation_from_state(row)
            if (
                delegation.owner_spec_id not in active_specs
                or delegation.delegate_spec_id not in active_specs
            ):
                continue
            owner = ownership_index.get(delegation.path)
            if owner is None or owner[0] != delegation.owner_spec_id:
                continue
            delegations.append(delegation)
        delegations.sort(key=lambda item: (item.path, item.owner_spec_id, item.delegate_spec_id))
        return tuple(delegations)

    def _active_coordination(
        self,
        state: dict[str, Any],
        ownership_index: dict[str, tuple[str, dict[str, Any]]],
    ) -> tuple[Coordination, ...]:
        active_specs = self._active_specs(state)
        coordination: list[Coordination] = []
        for row in self._shared_rows(self.persisted_coordination_root):
            if cast(str, row.get("status")) != "active":
                continue
            item = self._coordination_from_state(row)
            if item.owner_spec_id not in active_specs:
                continue
            owner = ownership_index.get(item.path)
            if owner is None or owner[0] != item.owner_spec_id:
                continue
            coordination.append(item)
        coordination.sort(key=lambda item: (item.path, item.owner_spec_id))
        return tuple(coordination)

    def _active_specs(self, state: dict[str, Any]) -> set[str]:
        return {
            spec_id
            for spec_id, spec_data in cast(dict[str, dict[str, Any]], state["specs"]).items()
            if cast(str, spec_data["status"]) == "active"
        }

    def _approved_owned_paths_by_spec(self, state: dict[str, Any]) -> dict[str, set[str]]:
        indexed_files = {
            path
            for path, node_data in cast(dict[str, dict[str, Any]], state["code_nodes"]).items()
            if cast(str, node_data["kind"]) == "file"
        }
        approved: dict[str, set[str]] = {}
        for proposal in self._load_proposal_rows().values():
            if proposal["status"] != "approved":
                continue
            path = cast(str, proposal["path"])
            if path not in indexed_files:
                continue
            spec_id = cast(str, proposal["spec_id"])
            approved.setdefault(spec_id, set()).add(path)
        return approved

    def _ownership_index(
        self,
        state: dict[str, Any],
    ) -> dict[str, tuple[str, dict[str, Any]]]:
        specs = cast(dict[str, dict[str, Any]], state["specs"])
        approved_paths_by_spec = self._approved_owned_paths_by_spec(state)
        ownership_index: dict[str, tuple[str, dict[str, Any]]] = {}
        for spec_id, spec_data in specs.items():
            if cast(str, spec_data["status"]) != "active":
                continue
            governs = cast(dict[str, dict[str, Any]], spec_data["governs"])
            owned_paths = set(governs.keys()) | approved_paths_by_spec.get(spec_id, set())
            for path in sorted(owned_paths):
                existing = ownership_index.get(path)
                if existing is not None and existing[0] != spec_id:
                    other_spec_id, other_spec_data = existing
                    raise SpecValidationError(
                        "active ownership overlap detected for "
                        f"{path}: {other_spec_id} ({cast(str, other_spec_data['source_path'])}) "
                        f"and {spec_id} ({cast(str, spec_data['source_path'])})"
                    )
                ownership_index[path] = (spec_id, spec_data)
        return ownership_index

    def _owned_paths_for_spec(self, spec_id: str, state: dict[str, Any]) -> tuple[str, ...]:
        spec_data = cast(dict[str, Any], state["specs"][spec_id])
        governs = cast(dict[str, dict[str, Any]], spec_data["governs"])
        owned_paths = set(governs.keys())
        owned_paths.update(self._approved_owned_paths_by_spec(state).get(spec_id, set()))
        return tuple(sorted(owned_paths))

    def _build_governing_spec(self, spec_id: str, spec_data: dict[str, Any]) -> GoverningSpec:
        governs = cast(dict[str, dict[str, Any]], spec_data["governs"])
        selectors = tuple(
            selector
            for selector in sorted(
                {
                    cast(str, edge_data["selector"])
                    for edge_data in governs.values()
                    if edge_data.get("selector") is not None
                }
            )
        )
        return GoverningSpec(
            id=spec_id,
            source_path=cast(str, spec_data["source_path"]),
            source_text=cast(str, spec_data["source_text"]),
            previous_source_text=cast(str | None, spec_data.get("previous_source_text")),
            has_local_snapshot_history=bool(spec_data.get("has_local_snapshot_history", False)),
            title=cast(str, spec_data["title"]),
            text=cast(str, spec_data["text"]),
            priority=self._default_priority(governs),
            selectors=selectors,
        )

    def _assert_active_spec(self, state: dict[str, Any], spec_id: str) -> None:
        spec_data = cast(dict[str, Any] | None, state["specs"].get(spec_id))
        if spec_data is None:
            raise EntityNotFoundError(f"spec not found: {spec_id}")
        if cast(str, spec_data["status"]) != "active":
            raise SpecValidationError(f"spec must be active: {spec_id}")

    def _assert_active_owned_path(
        self,
        state: dict[str, Any],
        ownership_index: dict[str, tuple[str, dict[str, Any]]],
        owner_spec_id: str,
        path: str,
    ) -> None:
        self._assert_active_spec(state, owner_spec_id)
        owner = ownership_index.get(path)
        if owner is None:
            raise SpecValidationError(f"{path} is not owned by any active spec")
        if owner[0] != owner_spec_id:
            raise SpecValidationError(f"{path} is owned by {owner[0]}, not {owner_spec_id}")

    def _clear_directory(self, path: Path) -> None:
        if not path.exists():
            return
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        path.rmdir()


def _empty_state() -> dict[str, Any]:
    return {
        "code_nodes": {},
        "specs": {},
        "decisions": {},
    }
