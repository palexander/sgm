from __future__ import annotations

import subprocess
from pathlib import Path

from tests.integration.helpers import create_sample_repo, run_cli


def test_init_accepts_worktree_root(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)
    worktree_root = tmp_path / "sample-worktree"
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "worktree-init", str(worktree_root)],
        cwd=sample_repo.root,
        check=True,
    )

    result = run_cli(sgm_executable, worktree_root, "init")

    assert result.returncode == 0
    assert "[INIT] sgm workspace prepared" in result.stdout
    assert (worktree_root / ".sgm" / "work").is_dir()
    assert (worktree_root / "AGENTS.md").is_file()


def test_validate_accepts_worktree_root(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)
    worktree_root = tmp_path / "sample-worktree"
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "worktree-validate", str(worktree_root)],
        cwd=sample_repo.root,
        check=True,
    )

    result = run_cli(sgm_executable, worktree_root, "validate", "--no-record")

    assert result.returncode == 0
    assert "[PASS] no changed files for spec-001" in result.stdout
