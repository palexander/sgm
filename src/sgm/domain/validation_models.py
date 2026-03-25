from __future__ import annotations

from dataclasses import dataclass

from sgm.domain.proposal_models import Proposal
from sgm.domain.spec_models import GoverningSpec


@dataclass(frozen=True, slots=True)
class ValidationWarning:
    path: str
    proposal: Proposal


@dataclass(frozen=True, slots=True)
class ValidationReport:
    spec: GoverningSpec
    changed_files: tuple[str, ...]
    governed_files: tuple[str, ...]
    warning_files: tuple[ValidationWarning, ...]
    error_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ValidationSuiteReport:
    reports: tuple[ValidationReport, ...]
