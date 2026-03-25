from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import uuid4

from sgm.domain.errors import EntityNotFoundError, InfrastructureError
from sgm.domain.models import (
    ApprovalResult,
    Assertion,
    AssertionDocument,
    AssertionKind,
    AssertionSeverity,
    CodeNode,
    ComplianceSnapshot,
    ContextResponse,
    DecisionDocument,
    DecisionStatus,
    GoverningSpec,
    PersistResult,
    Proposal,
    ProposalListResult,
    ProposalStatus,
    ProposeResult,
    RejectResult,
    RelatedDecision,
    SpecDocument,
    SyncDecisionResult,
    SyncFilesResult,
    SyncSpecResult,
)
from sgm.domain.scoring import compute_score
from sgm.domain.selectors import matches_selector


class GraphRepository(Protocol):
    def reset(self) -> None: ...
    def sync_files(self, scan_root: str, nodes: tuple[CodeNode, ...]) -> SyncFilesResult: ...
    def sync_spec(self, spec: SpecDocument) -> SyncSpecResult: ...
    def sync_decision(self, decision: DecisionDocument) -> SyncDecisionResult: ...
    def prune_specs(self, source_paths: tuple[str, ...]) -> None: ...
    def prune_decisions(self, source_paths: tuple[str, ...]) -> None: ...
    def get_context(self, target_path: str) -> ContextResponse: ...
    def get_assertions_for_path(self, target_path: str) -> dict[str, tuple[Assertion, ...]]: ...
    def get_existing_scores(self, target_path: str) -> dict[str, ComplianceSnapshot]: ...
    def record_validation(
        self,
        spec_id: str,
        target_path: str,
        total_checks: int,
        passed_checks: int,
        failed_errors: int,
        failed_warnings: int,
    ) -> ComplianceSnapshot: ...
    def create_proposal(
        self,
        proposal_id: str,
        spec_id: str,
        path: str,
        reason: str,
    ) -> ProposeResult: ...
    def list_proposals(self, status: ProposalStatus | None) -> ProposalListResult: ...
    def approve_proposal(self, proposal_id: str) -> ApprovalResult: ...
    def reject_proposal(self, proposal_id: str, review_reason: str | None) -> RejectResult: ...
    def persist(self) -> PersistResult: ...


@dataclass(slots=True)
class FileRepository:
    repo_root: Path
    work_root: Path = field(init=False)
    state_path: Path = field(init=False)
    work_proposals_root: Path = field(init=False)
    work_validations_root: Path = field(init=False)
    persisted_root: Path = field(init=False)
    persisted_proposals_root: Path = field(init=False)
    persisted_validations_root: Path = field(init=False)

    def __post_init__(self) -> None:
        self.work_root = self.repo_root / ".sgm" / "work"
        self.state_path = self.work_root / "state.json"
        self.work_proposals_root = self.work_root / "proposals"
        self.work_validations_root = self.work_root / "validations"
        self.persisted_root = self.repo_root / ".sgm" / "persisted"
        self.persisted_proposals_root = self.persisted_root / "proposals"
        self.persisted_validations_root = self.persisted_root / "validations"

    def reset(self) -> None:
        self._write_state(_empty_state())
        self._clear_directory(self.work_proposals_root)
        self._clear_directory(self.work_validations_root)

    def sync_files(self, scan_root: str, nodes: tuple[CodeNode, ...]) -> SyncFilesResult:
        state = self._load_state()
        prefix: str = "" if scan_root == "." else f"{scan_root.rstrip('/')}/"
        existing_paths: set[str] = {
            path
            for path in state["code_nodes"]
            if path == scan_root or path.startswith(prefix)
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
            "title": spec.title,
            "version": spec.version,
            "text": spec.text,
            "status": spec.status,
            "author": spec.author,
            "warn_below": spec.warn_below,
            "assertions": [
                self._assertion_document_to_state(assertion) for assertion in spec.assertions
            ],
            "governs": governs,
        }
        self._write_state(state)
        return SyncSpecResult(
            spec_id=spec.id,
            assertion_count=len(spec.assertions),
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

    def get_context(self, target_path: str) -> ContextResponse:
        state = self._load_state()
        if target_path not in state["code_nodes"]:
            return ContextResponse(
                target_path=target_path,
                specs=(),
                decisions=(),
                siblings=(),
                indexed=False,
            )

        compliance_by_spec = self.get_existing_scores(target_path)
        approved_paths = self._approved_paths_by_spec()

        specs: list[GoverningSpec] = []
        for spec_id, spec_data in state["specs"].items():
            if spec_data["status"] != "active":
                continue
            governs = cast(dict[str, Any], spec_data["governs"])
            selector_edge = cast(dict[str, Any] | None, governs.get(target_path))
            proposal_governed = target_path in approved_paths.get(spec_id, set())
            if selector_edge is None and not proposal_governed:
                continue
            priority = (
                int(selector_edge["priority"])
                if selector_edge is not None
                else self._default_priority(governs)
            )
            compliance_data = compliance_by_spec.get(spec_id)
            specs.append(
                GoverningSpec(
                    id=spec_id,
                    source_path=cast(str, spec_data["source_path"]),
                    source_text=cast(str, spec_data["source_text"]),
                    previous_source_text=cast(str | None, spec_data.get("previous_source_text")),
                    title=cast(str, spec_data["title"]),
                    version=int(spec_data["version"]),
                    text=cast(str, spec_data["text"]),
                    warn_below=float(spec_data["warn_below"]),
                    priority=priority,
                    compliance_score=(
                        compliance_data.score if compliance_data is not None else None
                    ),
                    passed_checks=(
                        compliance_data.passed_checks if compliance_data is not None else None
                    ),
                    total_checks=(
                        compliance_data.total_checks if compliance_data is not None else None
                    ),
                )
            )
        specs.sort(key=lambda spec: (spec.priority, spec.id))

        siblings: tuple[str, ...] = ()
        if specs:
            sibling_paths: set[str] = set()
            for spec in specs:
                spec_data = cast(dict[str, Any], state["specs"][spec.id])
                selector_paths = set(cast(dict[str, Any], spec_data["governs"]).keys())
                sibling_paths.update(selector_paths)
                sibling_paths.update(approved_paths.get(spec.id, set()))
            sibling_paths.discard(target_path)
            siblings = tuple(sorted(sibling_paths))

        decisions: list[RelatedDecision] = []
        for decision_id, decision_data in state["decisions"].items():
            if decision_data["status"] != "active":
                continue
            if target_path not in cast(list[str], decision_data["informs"]):
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

        return ContextResponse(
            target_path=target_path,
            specs=tuple(specs),
            decisions=tuple(decisions),
            siblings=siblings,
            indexed=True,
        )

    def get_assertions_for_path(self, target_path: str) -> dict[str, tuple[Assertion, ...]]:
        state = self._load_state()
        if target_path not in state["code_nodes"]:
            raise EntityNotFoundError("target file missing from graph")

        approved_paths = self._approved_paths_by_spec()
        result: dict[str, tuple[Assertion, ...]] = {}
        for spec_id, spec_data in state["specs"].items():
            governs = cast(dict[str, Any], spec_data["governs"])
            if spec_data["status"] != "active":
                continue
            if target_path not in governs and target_path not in approved_paths.get(spec_id, set()):
                continue
            assertion_rows = cast(list[dict[str, Any]], spec_data["assertions"])
            assertions = tuple(
                Assertion(
                    id=cast(str, row["id"]),
                    rule=cast(str, row["rule"]),
                    hint=cast(str | None, row["hint"]),
                    kind=cast(AssertionKind, row["kind"]),
                    severity=cast(AssertionSeverity, row["severity"]),
                    check=cast(str, row["check"]),
                    config_json=cast(str, row["config_json"]),
                )
                for row in sorted(assertion_rows, key=lambda row: cast(str, row["id"]))
            )
            result[spec_id] = assertions
        return result

    def get_existing_scores(self, target_path: str) -> dict[str, ComplianceSnapshot]:
        snapshots: dict[str, ComplianceSnapshot] = {}
        for spec_id, record in self._iter_validation_records():
            if record.path != target_path:
                continue
            previous = snapshots.get(spec_id)
            if previous is None:
                total_checks = record.total_checks
                passed_checks = record.passed_checks
                failed_errors = record.failed_errors
                failed_warnings = record.failed_warnings
            else:
                total_checks = previous.total_checks + record.total_checks
                passed_checks = previous.passed_checks + record.passed_checks
                failed_errors = previous.failed_errors + record.failed_errors
                failed_warnings = previous.failed_warnings + record.failed_warnings
            snapshots[spec_id] = ComplianceSnapshot(
                total_checks=total_checks,
                passed_checks=passed_checks,
                failed_errors=failed_errors,
                failed_warnings=failed_warnings,
                score=compute_score(
                    passed_checks=passed_checks,
                    failed_errors=failed_errors,
                    failed_warnings=failed_warnings,
                ),
            )
        return snapshots

    def record_validation(
        self,
        spec_id: str,
        target_path: str,
        total_checks: int,
        passed_checks: int,
        failed_errors: int,
        failed_warnings: int,
    ) -> ComplianceSnapshot:
        state = self._load_state()
        spec_data = cast(dict[str, Any] | None, state["specs"].get(spec_id))
        if spec_data is None:
            raise EntityNotFoundError(f"spec not found: {spec_id}")
        record_path = self.work_validations_root / spec_id / (
            f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}.json"
        )
        payload = {
            "spec_id": spec_id,
            "path": target_path,
            "source_path": cast(str, spec_data["source_path"]),
            "version": int(spec_data["version"]),
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "failed_errors": failed_errors,
            "failed_warnings": failed_warnings,
            "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        self._write_json_file(record_path, payload)
        updated = self.get_existing_scores(target_path).get(spec_id)
        if updated is None:
            raise InfrastructureError("validation record was not persisted")
        return updated

    def create_proposal(
        self,
        proposal_id: str,
        spec_id: str,
        path: str,
        reason: str,
    ) -> ProposeResult:
        state = self._load_state()
        spec_data = cast(dict[str, Any] | None, state["specs"].get(spec_id))
        if spec_data is None:
            raise EntityNotFoundError(f"spec not found: {spec_id}")
        if path not in state["code_nodes"]:
            raise EntityNotFoundError(f"file not indexed: {path}")
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
        self._write_json_file(self.work_proposals_root / f"{proposal_id}.json", payload)
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
        self._write_json_file(proposal_path, proposal)
        return ApprovalResult(proposal_id=proposal_id, spec_id=spec_id, path=path)

    def reject_proposal(self, proposal_id: str, review_reason: str | None) -> RejectResult:
        proposal_path, proposal = self._proposal_record(proposal_id)
        if proposal["status"] != "pending":
            raise EntityNotFoundError(f"pending proposal not found: {proposal_id}")
        proposal["status"] = "rejected"
        proposal["reviewed_at"] = datetime.now().isoformat(timespec="seconds")
        proposal["review_reason"] = review_reason
        self._write_json_file(proposal_path, proposal)
        return RejectResult(proposal_id=proposal_id, review_reason=review_reason)

    def persist(self) -> PersistResult:
        persisted_validations = self._persist_files(
            source_root=self.work_validations_root,
            target_root=self.persisted_validations_root,
        )
        persisted_proposals = self._persist_files(
            source_root=self.work_proposals_root,
            target_root=self.persisted_proposals_root,
        )
        return PersistResult(
            persisted_validations=persisted_validations,
            persisted_proposals=persisted_proposals,
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

    def _assertion_document_to_state(self, assertion: AssertionDocument) -> dict[str, Any]:
        return {
            "id": assertion.id,
            "rule": assertion.rule,
            "hint": assertion.hint,
            "kind": assertion.kind,
            "severity": assertion.severity,
            "check": assertion.check,
            "config_json": json.dumps(assertion.config, sort_keys=True),
        }

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

    def _iter_validation_records(self) -> tuple[tuple[str, _ValidationRecord], ...]:
        records: list[tuple[str, _ValidationRecord]] = []
        for root in (self.persisted_validations_root, self.work_validations_root):
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*.json")):
                payload = self._load_json_file(path)
                spec_id = cast(str, payload["spec_id"])
                records.append(
                    (
                        spec_id,
                        _ValidationRecord(
                            path=cast(str, payload["path"]),
                            total_checks=int(payload["total_checks"]),
                            passed_checks=int(payload["passed_checks"]),
                            failed_errors=int(payload["failed_errors"]),
                            failed_warnings=int(payload["failed_warnings"]),
                        ),
                    )
                )
        return tuple(records)

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

    def _default_priority(self, governs: dict[str, Any]) -> int:
        priorities = [int(edge["priority"]) for edge in governs.values()]
        return min(priorities) if priorities else 1

    def _persist_files(self, source_root: Path, target_root: Path) -> int:
        if not source_root.is_dir():
            return 0
        persisted = 0
        for path in sorted(source_root.rglob("*.json")):
            relative_path = path.relative_to(source_root)
            target_path = target_root / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists():
                path.unlink()
                continue
            path.replace(target_path)
            persisted += 1
        self._prune_empty_directories(source_root)
        return persisted

    def _load_json_file(self, path: Path) -> dict[str, Any]:
        try:
            raw_payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise InfrastructureError(f"failed to read state: {error}") from error
        if not isinstance(raw_payload, dict):
            raise InfrastructureError("state file must contain a mapping")
        return cast(dict[str, Any], raw_payload)

    def _clear_directory(self, path: Path) -> None:
        if not path.exists():
            return
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        path.rmdir()

    def _prune_empty_directories(self, root: Path) -> None:
        if not root.exists():
            return
        for path in sorted(root.rglob("*"), reverse=True):
            if path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    continue


@dataclass(frozen=True, slots=True)
class _ValidationRecord:
    path: str
    total_checks: int
    passed_checks: int
    failed_errors: int
    failed_warnings: int


def _empty_state() -> dict[str, Any]:
    return {
        "code_nodes": {},
        "specs": {},
        "decisions": {},
    }
