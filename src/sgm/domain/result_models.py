from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SyncDecisionResult:
    decision_id: str
    informed_count: int
    selectors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SyncFilesResult:
    root: str
    scanned_paths: int


@dataclass(frozen=True, slots=True)
class SyncSpecResult:
    spec_id: str
    governed_count: int
    selectors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InitOffer:
    target: str
    message: str


@dataclass(frozen=True, slots=True)
class InitResult:
    created_directories: tuple[str, ...]
    created_files: tuple[str, ...]
    updated_files: tuple[str, ...]
    offers: tuple[InitOffer, ...]
    installed_hooks: tuple[str, ...] = ()
