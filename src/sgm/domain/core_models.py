from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

ExitCode = Literal[0, 1, 2, 3]
SpecStatus = Literal["active", "deprecated"]
DecisionStatus = Literal["draft", "active", "superseded"]
CodeNodeKind = Literal["file", "directory"]
ProposalStatus = Literal["pending", "approved", "rejected"]
SharedRecordStatus = Literal["active", "revoked"]


@dataclass(frozen=True, slots=True)
class CodeNode:
    id: str
    path: str
    kind: CodeNodeKind
    name: str
    last_modified: datetime


@dataclass(frozen=True, slots=True)
class RepoContext:
    root: Path
