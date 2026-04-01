from __future__ import annotations

from pathlib import Path

import pytest

from sgm.domain.errors import RepoRootError
from sgm.domain.paths import ensure_repo_root


def test_ensure_repo_root_accepts_git_directory(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)

    repo_context = ensure_repo_root(repo_root)

    assert repo_context.root == repo_root


def test_ensure_repo_root_accepts_worktree_gitfile(tmp_path: Path) -> None:
    worktree_root = tmp_path / "worktree"
    worktree_root.mkdir()
    (worktree_root / ".git").write_text("gitdir: /tmp/worktrees/example\n", encoding="utf-8")

    repo_context = ensure_repo_root(worktree_root)

    assert repo_context.root == worktree_root


def test_ensure_repo_root_rejects_nested_directory_without_git_marker(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)
    nested_dir = repo_root / "src"
    nested_dir.mkdir()

    with pytest.raises(RepoRootError, match=r"sgm must run from repo root \(.git not found\)"):
        ensure_repo_root(nested_dir)
