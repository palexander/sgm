from __future__ import annotations

from pathlib import Path, PurePosixPath

from sgm.domain.errors import RepoRootError
from sgm.domain.models import RepoContext


def ensure_repo_root(cwd: Path) -> RepoContext:
    if not (cwd / ".git").is_dir():
        raise RepoRootError("sgm must run from repo root (.git/ not found)")
    return RepoContext(root=cwd)


def to_repo_relative_posix(repo_root: Path, raw_path: str) -> str:
    input_path: Path = Path(raw_path)
    if input_path.is_absolute():
        resolved_path: Path = input_path.resolve()
    else:
        resolved_path = (repo_root / input_path).resolve()
    relative_path: Path = resolved_path.relative_to(repo_root.resolve())
    return PurePosixPath(relative_path.as_posix()).as_posix()


def normalize_scan_root(repo_root: Path, raw_path: str | None) -> str:
    if raw_path is None:
        return "."
    normalized: str = to_repo_relative_posix(repo_root, raw_path)
    return normalized
