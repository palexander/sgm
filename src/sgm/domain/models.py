from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

ExitCode = Literal[0, 1, 2, 3]
AssertionKind = Literal["structural"]
AssertionSeverity = Literal["error", "warning"]
SpecStatus = Literal["draft", "active", "deprecated"]
CodeNodeKind = Literal["file", "directory"]
ProposalStatus = Literal["pending", "approved", "rejected"]
ValidationOutcome = Literal["pass", "fail", "inconclusive"]


@dataclass(frozen=True, slots=True)
class GraphConnectionConfig:
    host: str
    port: int
    username: str
    password: str
    encrypted: bool
    lazy: bool


@dataclass(frozen=True, slots=True)
class Assertion:
    id: str
    rule: str
    hint: str | None
    kind: AssertionKind
    severity: AssertionSeverity
    check: str
    config_json: str


@dataclass(frozen=True, slots=True)
class SpecDocument:
    id: str
    source_path: str
    source_text: str
    title: str
    version: int
    text: str
    status: SpecStatus
    author: str
    warn_below: float
    assertions: tuple[AssertionDocument, ...]
    governs: tuple[GovernanceSelector, ...]


@dataclass(frozen=True, slots=True)
class AssertionDocument:
    id: str
    rule: str
    hint: str | None
    kind: AssertionKind
    severity: AssertionSeverity
    check: str
    config: dict[str, list[str]]


@dataclass(frozen=True, slots=True)
class GovernanceSelector:
    selector: str
    priority: int


@dataclass(frozen=True, slots=True)
class CodeNode:
    id: str
    path: str
    kind: CodeNodeKind
    name: str
    last_modified: datetime


@dataclass(frozen=True, slots=True)
class GoverningSpec:
    id: str
    source_path: str
    source_text: str
    previous_source_text: str | None
    title: str
    version: int
    text: str
    warn_below: float
    priority: int
    compliance_score: float | None
    passed_checks: int | None
    total_checks: int | None
    spec_delta: SpecDelta | None = None


@dataclass(frozen=True, slots=True)
class SpecDelta:
    spec_id: str
    source_path: str
    diff_lines: tuple[str, ...]
    current_exists: bool


@dataclass(frozen=True, slots=True)
class ComplianceSnapshot:
    total_checks: int
    passed_checks: int
    failed_errors: int
    failed_warnings: int
    score: float


@dataclass(frozen=True, slots=True)
class Proposal:
    id: str
    spec_id: str
    path: str
    reason: str
    status: ProposalStatus
    created_at: datetime
    reviewed_at: datetime | None
    review_reason: str | None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    assertion: Assertion
    outcome: ValidationOutcome
    details: str | None


@dataclass(frozen=True, slots=True)
class ValidationSummary:
    spec_id: str
    results: tuple[ValidationResult, ...]
    total_checks: int
    passed_checks: int
    failed_errors: int
    failed_warnings: int
    inconclusive_warnings: int


@dataclass(frozen=True, slots=True)
class ValidationReport:
    spec_summaries: tuple[ValidationSummary, ...]
    spec_deltas: tuple[SpecDelta, ...] = ()


@dataclass(frozen=True, slots=True)
class ContextResponse:
    target_path: str
    specs: tuple[GoverningSpec, ...]
    siblings: tuple[str, ...]
    indexed: bool


@dataclass(frozen=True, slots=True)
class SyncFilesResult:
    root: str
    scanned_paths: int


@dataclass(frozen=True, slots=True)
class SyncSpecResult:
    spec_id: str
    assertion_count: int
    governed_count: int
    selectors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProposeResult:
    created: bool
    proposal_id: str | None
    spec_id: str
    spec_title: str | None
    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class ProposalListResult:
    proposals: tuple[Proposal, ...]
    status_filter: ProposalStatus | None


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    proposal_id: str
    spec_id: str
    path: str


@dataclass(frozen=True, slots=True)
class RejectResult:
    proposal_id: str
    review_reason: str | None


@dataclass(frozen=True, slots=True)
class RepoContext:
    root: Path


@dataclass(frozen=True, slots=True)
class ImportScan:
    imports: tuple[str, ...]
    inconclusive: bool
