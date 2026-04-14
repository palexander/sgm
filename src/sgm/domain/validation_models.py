from __future__ import annotations

from dataclasses import dataclass

from sgm.domain.context_models import FocusWarning
from sgm.domain.proposal_models import Proposal
from sgm.domain.spec_models import GoverningSpec


@dataclass(frozen=True, slots=True)
class ValidationWarning:
    path: str
    proposal: Proposal


@dataclass(frozen=True, slots=True)
class ValidationNote:
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationError:
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationReport:
    spec: GoverningSpec
    changed_files: tuple[str, ...]
    editable_files: tuple[str, ...]
    coordination_files: tuple[str, ...]
    warning_files: tuple[ValidationWarning, ...]
    note_files: tuple[ValidationNote, ...]
    error_files: tuple[ValidationError, ...]
    focus_warning: FocusWarning | None = None


@dataclass(frozen=True, slots=True)
class ValidationSuiteReport:
    reports: tuple[ValidationReport, ...]
