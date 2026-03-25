from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, cast

from gqlalchemy import Memgraph

from sgm.adapters.spec_loader import serialize_assertion_config
from sgm.domain.errors import EntityNotFoundError, InfrastructureError
from sgm.domain.models import (
    ApprovalResult,
    Assertion,
    AssertionKind,
    AssertionSeverity,
    CodeNode,
    ComplianceSnapshot,
    ContextResponse,
    GoverningSpec,
    GraphConnectionConfig,
    Proposal,
    ProposalListResult,
    ProposalStatus,
    ProposeResult,
    RejectResult,
    SpecDocument,
    SyncFilesResult,
    SyncSpecResult,
)
from sgm.domain.selectors import matches_selector


class GraphRepository(Protocol):
    def reset(self) -> None: ...
    def sync_files(self, scan_root: str, nodes: tuple[CodeNode, ...]) -> SyncFilesResult: ...
    def sync_spec(self, spec: SpecDocument) -> SyncSpecResult: ...
    def prune_specs(self, source_paths: tuple[str, ...]) -> None: ...
    def get_context(self, target_path: str) -> ContextResponse: ...
    def get_assertions_for_path(self, target_path: str) -> dict[str, tuple[Assertion, ...]]: ...
    def get_existing_scores(self, target_path: str) -> dict[str, ComplianceSnapshot]: ...
    def apply_compliance_update(
        self,
        spec_id: str,
        target_path: str,
        snapshot: ComplianceSnapshot,
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


@dataclass(slots=True)
class MemgraphRepository:
    config: GraphConnectionConfig
    _db: Memgraph = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._db = Memgraph(
            host=self.config.host,
            port=self.config.port,
            username=self.config.username,
            password=self.config.password,
            encrypted=self.config.encrypted,
            lazy=self.config.lazy,
        )

    def reset(self) -> None:
        self._execute("MATCH (n) DETACH DELETE n")

    def sync_files(self, scan_root: str, nodes: tuple[CodeNode, ...]) -> SyncFilesResult:
        prefix: str = "" if scan_root == "." else f"{scan_root.rstrip('/')}/"
        existing: list[dict[str, Any]] = self._fetch(
            "MATCH (c:CodeNode) "
            "WHERE c.path = $scan_root OR c.path STARTS WITH $prefix "
            "RETURN c.path AS path",
            {"scan_root": scan_root, "prefix": prefix},
        )
        existing_paths: set[str] = {cast(str, row["path"]) for row in existing}
        current_paths: set[str] = {node.path for node in nodes}
        stale_paths: set[str] = existing_paths - current_paths

        with self._transaction():
            for node in nodes:
                self._execute(
                    "MERGE (c:CodeNode {id: $id}) "
                    "SET c.path = $path, "
                    "    c.kind = $kind, "
                    "    c.name = $name, "
                    "    c.last_modified = localDateTime($last_modified) ",
                    {
                        "id": node.id,
                        "path": node.path,
                        "kind": node.kind,
                        "name": node.name,
                        "last_modified": node.last_modified.isoformat(timespec="seconds"),
                    },
                )
            for stale_path in stale_paths:
                self._execute(
                    "MATCH (c:CodeNode {path: $path}) DETACH DELETE c",
                    {"path": stale_path},
                )
        return SyncFilesResult(root=scan_root, scanned_paths=len(nodes))

    def sync_spec(self, spec: SpecDocument) -> SyncSpecResult:
        existing_spec_rows: list[dict[str, Any]] = self._fetch(
            "MATCH (s:Spec {id: $id}) "
            "RETURN s.source_text AS source_text",
            {"id": spec.id},
        )
        previous_source_text: str | None = None
        if existing_spec_rows:
            existing_source_text: str | None = cast(
                str | None, existing_spec_rows[0].get("source_text")
            )
            if existing_source_text != spec.source_text:
                previous_source_text = existing_source_text

        code_nodes: list[dict[str, Any]] = self._fetch(
            "MATCH (c:CodeNode {kind: 'file'}) RETURN c.path AS path ORDER BY c.path"
        )
        matched_paths: dict[str, int] = {}
        for selector in spec.governs:
            for row in code_nodes:
                code_path: str = cast(str, row["path"])
                if matches_selector(path=code_path, selector=selector.selector):
                    existing_priority: int | None = matched_paths.get(code_path)
                    if existing_priority is None or selector.priority < existing_priority:
                        matched_paths[code_path] = selector.priority

        with self._transaction():
            self._execute(
                "MERGE (s:Spec {id: $id}) "
                "SET s.source_path = $source_path, "
                "    s.source_text = $source_text, "
                "    s.previous_source_text = $previous_source_text, "
                "    s.title = $title, "
                "    s.version = $version, "
                "    s.text = $text, "
                "    s.status = $status, "
                "    s.author = $author, "
                "    s.warn_below = $warn_below",
                {
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
                },
            )

            self._execute(
                "MATCH (:Spec {id: $id})-[r:CONTAINS]->(:Assertion) DELETE r",
                {"id": spec.id},
            )
            for assertion in spec.assertions:
                self._execute(
                    "MERGE (a:Assertion {id: $id}) "
                    "SET a.rule = $rule, "
                    "    a.hint = $hint, "
                    "    a.kind = $kind, "
                    "    a.severity = $severity, "
                    "    a.check = $check, "
                    "    a.config_json = $config_json",
                    {
                        "id": assertion.id,
                        "rule": assertion.rule,
                        "hint": assertion.hint,
                        "kind": assertion.kind,
                        "severity": assertion.severity,
                        "check": assertion.check,
                        "config_json": serialize_assertion_config(assertion.config),
                    },
                )
                self._execute(
                    "MATCH (s:Spec {id: $spec_id}), (a:Assertion {id: $assertion_id}) "
                    "MERGE (s)-[:CONTAINS]->(a)",
                    {"spec_id": spec.id, "assertion_id": assertion.id},
                )

            self._execute(
                "MATCH (:Spec {id: $id})-[g:GOVERNS]->(:CodeNode) "
                "WHERE g.selector IS NOT NULL DELETE g",
                {"id": spec.id},
            )

            for path, priority in matched_paths.items():
                selector_value: str = next(
                    selector.selector
                    for selector in spec.governs
                    if matches_selector(path=path, selector=selector.selector)
                    and selector.priority == priority
                )
                self._execute(
                    "MATCH (s:Spec {id: $spec_id}), (c:CodeNode {path: $path}) "
                    "MERGE (s)-[g:GOVERNS]->(c) "
                    "SET g.priority = $priority, "
                    "    g.selector = $selector",
                    {
                        "spec_id": spec.id,
                        "path": path,
                        "priority": priority,
                        "selector": selector_value,
                    },
                )
                self._execute(
                    "MATCH (s:Spec {id: $spec_id}), (c:CodeNode {path: $path}) "
                    "MERGE (s)-[h:COMPLIANCE]->(c) "
                    "ON CREATE SET h.total_checks = 0, "
                    "              h.passed_checks = 0, "
                    "              h.failed_errors = 0, "
                    "              h.failed_warnings = 0, "
                    "              h.score = 1.0",
                    {"spec_id": spec.id, "path": path},
                )

            self._execute(
                "MATCH (s:Spec {id: $spec_id})-[h:COMPLIANCE]->(c:CodeNode) "
                "WHERE NOT EXISTS((s)-[:GOVERNS]->(c)) DELETE h",
                {"spec_id": spec.id},
            )

        return SyncSpecResult(
            spec_id=spec.id,
            assertion_count=len(spec.assertions),
            governed_count=len(matched_paths),
            selectors=tuple(selector.selector for selector in spec.governs),
        )

    def prune_specs(self, source_paths: tuple[str, ...]) -> None:
        with self._transaction():
            self._execute(
                "MATCH (s:Spec) "
                "WHERE s.source_path IS NULL OR NOT (s.source_path IN $source_paths) "
                "DETACH DELETE s",
                {"source_paths": list(source_paths)},
            )
            self._execute(
                "MATCH (a:Assertion) "
                "WHERE NOT EXISTS((:Spec)-[:CONTAINS]->(a)) "
                "DETACH DELETE a"
            )

    def get_context(self, target_path: str) -> ContextResponse:
        indexed_rows: list[dict[str, Any]] = self._fetch(
            "MATCH (c:CodeNode {path: $path}) RETURN c.path AS path",
            {"path": target_path},
        )
        if not indexed_rows:
            return ContextResponse(
                target_path=target_path,
                specs=(),
                siblings=(),
                indexed=False,
            )

        spec_rows: list[dict[str, Any]] = self._fetch(
            "MATCH (s:Spec {status: 'active'})-[g:GOVERNS]->(c:CodeNode {path: $path}) "
            "OPTIONAL MATCH (s)-[h:COMPLIANCE]->(c) "
            "RETURN s.id AS id, "
            "       s.source_path AS source_path, "
            "       s.source_text AS source_text, "
            "       s.previous_source_text AS previous_source_text, "
            "       s.title AS title, "
            "       s.version AS version, "
            "       s.text AS text, "
            "       s.warn_below AS warn_below, "
            "       g.priority AS priority, "
            "       h.score AS score, "
            "       h.passed_checks AS passed_checks, "
            "       h.total_checks AS total_checks "
            "ORDER BY g.priority ASC, s.id ASC",
            {"path": target_path},
        )
        specs: tuple[GoverningSpec, ...] = tuple(
            GoverningSpec(
                id=cast(str, row["id"]),
                source_path=cast(str, row["source_path"]),
                source_text=cast(str, row["source_text"]),
                previous_source_text=cast(str | None, row.get("previous_source_text")),
                title=cast(str, row["title"]),
                version=cast(int, row["version"]),
                text=cast(str, row["text"]),
                warn_below=float(cast(float, row["warn_below"])),
                priority=cast(int, row["priority"]),
                compliance_score=_as_optional_float(row.get("score")),
                passed_checks=_as_optional_int(row.get("passed_checks")),
                total_checks=_as_optional_int(row.get("total_checks")),
            )
            for row in spec_rows
        )
        if not specs:
            return ContextResponse(
                target_path=target_path,
                specs=(),
                siblings=(),
                indexed=True,
            )

        sibling_rows: list[dict[str, Any]] = self._fetch(
            "MATCH (s:Spec)-[:GOVERNS]->(sibling:CodeNode) "
            "WHERE s.id IN $spec_ids AND sibling.path <> $path "
            "RETURN DISTINCT sibling.path AS path "
            "ORDER BY sibling.path ASC",
            {"spec_ids": [spec.id for spec in specs], "path": target_path},
        )
        siblings: tuple[str, ...] = tuple(cast(str, row["path"]) for row in sibling_rows)
        return ContextResponse(
            target_path=target_path,
            specs=specs,
            siblings=siblings,
            indexed=True,
        )

    def get_assertions_for_path(self, target_path: str) -> dict[str, tuple[Assertion, ...]]:
        spec_rows: list[dict[str, Any]] = self._fetch(
            "MATCH (s:Spec {status: 'active'})-[:GOVERNS]->(c:CodeNode {path: $path}) "
            "RETURN s.id AS spec_id "
            "ORDER BY s.id ASC",
            {"path": target_path},
        )
        if not spec_rows:
            indexed_rows: list[dict[str, Any]] = self._fetch(
                "MATCH (c:CodeNode {path: $path}) RETURN c.path AS path",
                {"path": target_path},
            )
            if not indexed_rows:
                raise EntityNotFoundError("target file missing from graph")
            return {}

        result: dict[str, tuple[Assertion, ...]] = {}
        for row in spec_rows:
            spec_id: str = cast(str, row["spec_id"])
            assertion_rows: list[dict[str, Any]] = self._fetch(
                "MATCH (s:Spec {id: $spec_id})-[:CONTAINS]->(a:Assertion) "
                "RETURN a.id AS id, "
                "       a.rule AS rule, "
                "       a.hint AS hint, "
                "       a.kind AS kind, "
                "       a.severity AS severity, "
                "       a.check AS check, "
                "       a.config_json AS config_json "
                "ORDER BY a.id ASC",
                {"spec_id": spec_id},
            )
            result[spec_id] = tuple(
                Assertion(
                    id=cast(str, assertion_row["id"]),
                    rule=cast(str, assertion_row["rule"]),
                    hint=cast(str | None, assertion_row["hint"]),
                    kind=cast(AssertionKind, assertion_row["kind"]),
                    severity=cast(AssertionSeverity, assertion_row["severity"]),
                    check=cast(str, assertion_row["check"]),
                    config_json=cast(str, assertion_row["config_json"]),
                )
                for assertion_row in assertion_rows
            )
        return result

    def get_existing_scores(self, target_path: str) -> dict[str, ComplianceSnapshot]:
        rows: list[dict[str, Any]] = self._fetch(
            "MATCH (s:Spec)-[h:COMPLIANCE]->(c:CodeNode {path: $path}) "
            "RETURN s.id AS spec_id, "
            "       h.total_checks AS total_checks, "
            "       h.passed_checks AS passed_checks, "
            "       h.failed_errors AS failed_errors, "
            "       h.failed_warnings AS failed_warnings, "
            "       h.score AS score",
            {"path": target_path},
        )
        return {
            cast(str, row["spec_id"]): ComplianceSnapshot(
                total_checks=cast(int, row["total_checks"]),
                passed_checks=cast(int, row["passed_checks"]),
                failed_errors=cast(int, row["failed_errors"]),
                failed_warnings=cast(int, row["failed_warnings"]),
                score=float(cast(float, row["score"])),
            )
            for row in rows
        }

    def apply_compliance_update(
        self,
        spec_id: str,
        target_path: str,
        snapshot: ComplianceSnapshot,
    ) -> ComplianceSnapshot:
        self._execute(
            "MATCH (s:Spec {id: $spec_id})-[h:COMPLIANCE]->(c:CodeNode {path: $path}) "
            "SET h.total_checks = $total_checks, "
            "    h.passed_checks = $passed_checks, "
            "    h.failed_errors = $failed_errors, "
            "    h.failed_warnings = $failed_warnings, "
            "    h.score = $score",
            {
                "spec_id": spec_id,
                "path": target_path,
                "total_checks": snapshot.total_checks,
                "passed_checks": snapshot.passed_checks,
                "failed_errors": snapshot.failed_errors,
                "failed_warnings": snapshot.failed_warnings,
                "score": snapshot.score,
            },
        )
        return snapshot

    def create_proposal(
        self,
        proposal_id: str,
        spec_id: str,
        path: str,
        reason: str,
    ) -> ProposeResult:
        spec_rows: list[dict[str, Any]] = self._fetch(
            "MATCH (s:Spec {id: $spec_id}) RETURN s.id AS id, s.title AS title",
            {"spec_id": spec_id},
        )
        if not spec_rows:
            raise EntityNotFoundError(f"spec not found: {spec_id}")
        indexed_rows: list[dict[str, Any]] = self._fetch(
            "MATCH (c:CodeNode {path: $path}) RETURN c.path AS path",
            {"path": path},
        )
        if not indexed_rows:
            raise EntityNotFoundError(f"file not indexed: {path}")
        governed_rows: list[dict[str, Any]] = self._fetch(
            "MATCH (:Spec {id: $spec_id})-[:GOVERNS]->(:CodeNode {path: $path}) RETURN 1 AS found",
            {"spec_id": spec_id, "path": path},
        )
        if governed_rows:
            return ProposeResult(
                created=False,
                proposal_id=None,
                spec_id=spec_id,
                spec_title=cast(str, spec_rows[0]["title"]),
                path=path,
                reason=reason,
            )
        self._execute(
            "CREATE (p:Proposal {"
            "  id: $proposal_id, "
            "  spec_id: $spec_id, "
            "  path: $path, "
            "  reason: $reason, "
            "  status: 'pending', "
            "  created_at: localDateTime($created_at), "
            "  reviewed_at: null, "
            "  review_reason: null"
            "})",
            {
                "proposal_id": proposal_id,
                "spec_id": spec_id,
                "path": path,
                "reason": reason,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
        return ProposeResult(
            created=True,
            proposal_id=proposal_id,
            spec_id=spec_id,
            spec_title=cast(str, spec_rows[0]["title"]),
            path=path,
            reason=reason,
        )

    def list_proposals(self, status: ProposalStatus | None) -> ProposalListResult:
        if status is None:
            rows: list[dict[str, Any]] = self._fetch(
                "MATCH (p:Proposal) "
                "RETURN p.id AS id, "
                "       p.spec_id AS spec_id, "
                "       p.path AS path, "
                "       p.reason AS reason, "
                "       p.status AS status, "
                "       p.created_at AS created_at, "
                "       p.reviewed_at AS reviewed_at, "
                "       p.review_reason AS review_reason "
                "ORDER BY p.created_at ASC, p.id ASC"
            )
        else:
            rows = self._fetch(
                "MATCH (p:Proposal {status: $status}) "
                "RETURN p.id AS id, "
                "       p.spec_id AS spec_id, "
                "       p.path AS path, "
                "       p.reason AS reason, "
                "       p.status AS status, "
                "       p.created_at AS created_at, "
                "       p.reviewed_at AS reviewed_at, "
                "       p.review_reason AS review_reason "
                "ORDER BY p.created_at ASC, p.id ASC",
                {"status": status},
            )
        proposals: tuple[Proposal, ...] = tuple(self._proposal_from_row(row) for row in rows)
        return ProposalListResult(proposals=proposals, status_filter=status)

    def approve_proposal(self, proposal_id: str) -> ApprovalResult:
        rows: list[dict[str, Any]] = self._fetch(
            "MATCH (p:Proposal {id: $proposal_id, status: 'pending'}) "
            "RETURN p.spec_id AS spec_id, p.path AS path",
            {"proposal_id": proposal_id},
        )
        if not rows:
            raise EntityNotFoundError(f"pending proposal not found: {proposal_id}")
        spec_id: str = cast(str, rows[0]["spec_id"])
        path: str = cast(str, rows[0]["path"])
        priority_rows: list[dict[str, Any]] = self._fetch(
            "MATCH (:Spec {id: $spec_id})-[g:GOVERNS]->(:CodeNode) "
            "RETURN min(g.priority) AS priority",
            {"spec_id": spec_id},
        )
        priority_value: int = (
            cast(int, priority_rows[0]["priority"])
            if priority_rows and priority_rows[0]["priority"] is not None
            else 1
        )
        with self._transaction():
            self._execute(
                "MATCH (s:Spec {id: $spec_id}), (c:CodeNode {path: $path}) "
                "MERGE (s)-[g:GOVERNS]->(c) "
                "SET g.priority = $priority, "
                "    g.selector = null",
                {"spec_id": spec_id, "path": path, "priority": priority_value},
            )
            self._execute(
                "MATCH (s:Spec {id: $spec_id}), (c:CodeNode {path: $path}) "
                "MERGE (s)-[h:COMPLIANCE]->(c) "
                "ON CREATE SET h.total_checks = 0, "
                "              h.passed_checks = 0, "
                "              h.failed_errors = 0, "
                "              h.failed_warnings = 0, "
                "              h.score = 1.0",
                {"spec_id": spec_id, "path": path},
            )
            self._execute(
                "MATCH (p:Proposal {id: $proposal_id}) "
                "SET p.status = 'approved', "
                "    p.reviewed_at = localDateTime($reviewed_at)",
                {
                    "proposal_id": proposal_id,
                    "reviewed_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
        return ApprovalResult(proposal_id=proposal_id, spec_id=spec_id, path=path)

    def reject_proposal(self, proposal_id: str, review_reason: str | None) -> RejectResult:
        rows: list[dict[str, Any]] = self._fetch(
            "MATCH (p:Proposal {id: $proposal_id, status: 'pending'}) RETURN p.id AS id",
            {"proposal_id": proposal_id},
        )
        if not rows:
            raise EntityNotFoundError(f"pending proposal not found: {proposal_id}")
        self._execute(
            "MATCH (p:Proposal {id: $proposal_id}) "
            "SET p.status = 'rejected', "
            "    p.reviewed_at = localDateTime($reviewed_at), "
            "    p.review_reason = $review_reason",
            {
                "proposal_id": proposal_id,
                "reviewed_at": datetime.now().isoformat(timespec="seconds"),
                "review_reason": review_reason,
            },
        )
        return RejectResult(proposal_id=proposal_id, review_reason=review_reason)

    def _proposal_from_row(self, row: dict[str, Any]) -> Proposal:
        return Proposal(
            id=cast(str, row["id"]),
            spec_id=cast(str, row["spec_id"]),
            path=cast(str, row["path"]),
            reason=cast(str, row["reason"]),
            status=cast(ProposalStatus, row["status"]),
            created_at=_to_datetime(row["created_at"]),
            reviewed_at=(
                _to_datetime(row["reviewed_at"])
                if row["reviewed_at"] is not None
                else None
            ),
            review_reason=cast(str | None, row["review_reason"]),
        )

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        try:
            self._execute("BEGIN")
            yield
            self._execute("COMMIT")
        except Exception as error:  # pragma: no cover - exercised in integration tests
            self._execute("ROLLBACK")
            raise InfrastructureError(str(error)) from error

    def _fetch(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            return list(self._db.execute_and_fetch(query, parameters or {}))
        except Exception as error:  # pragma: no cover - depends on external driver failure
            raise InfrastructureError(str(error)) from error

    def _execute(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        try:
            self._db.execute(query, parameters or {})
        except Exception as error:  # pragma: no cover - depends on external driver failure
            raise InfrastructureError(str(error)) from error


def _to_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise InfrastructureError(f"unexpected datetime value: {value!r}")


def _as_optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(cast(float, value))


def _as_optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(cast(int, value))
