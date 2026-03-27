from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sgm.domain.errors import InfrastructureError


@dataclass(frozen=True, slots=True)
class SystemAdapter:
    def new_proposal_id(self) -> str:
        return f"prop-{uuid4().hex[:6]}"

    def now(self) -> datetime:
        return datetime.now()

    def changed_files(self, repo_root: Path) -> tuple[str, ...]:
        status_output = self._git_status_porcelain(repo_root)
        changed_paths = self._paths_from_status_output(status_output)
        return tuple(sorted(dict.fromkeys(changed_paths)))

    def repo_file_inventory(self, repo_root: Path) -> tuple[str, ...]:
        try:
            tracked_process = subprocess.run(
                [
                    "git",
                    "ls-files",
                    "--cached",
                    "--others",
                    "--exclude-standard",
                    "-z",
                ],
                cwd=repo_root,
                check=True,
                text=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise InfrastructureError(f"failed to read git file inventory: {error}") from error
        inventory_paths: list[str] = []
        for raw_path in tracked_process.stdout.split("\0"):
            if raw_path == "":
                continue
            normalized_path: str = Path(raw_path).as_posix()
            if normalized_path == ".sgm" or normalized_path.startswith(".sgm/"):
                continue
            if "node_modules" in Path(normalized_path).parts:
                continue
            inventory_paths.append(normalized_path)
        return tuple(sorted(dict.fromkeys(inventory_paths)))

    def git_diff(self, repo_root: Path, relative_path: str) -> tuple[str, ...] | None:
        try:
            process = subprocess.run(
                [
                    "git",
                    "diff",
                    "--no-ext-diff",
                    "--",
                    relative_path,
                ],
                cwd=repo_root,
                check=True,
                text=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise InfrastructureError(f"failed to read git diff: {error}") from error
        diff_text = process.stdout.strip("\n")
        if diff_text == "":
            return None
        return tuple(diff_text.splitlines())

    def _git_status_porcelain(self, repo_root: Path) -> str:
        try:
            process = subprocess.run(
                [
                    "git",
                    "status",
                    "--porcelain",
                    "--untracked-files=all",
                ],
                cwd=repo_root,
                check=True,
                text=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise InfrastructureError(f"failed to read git status: {error}") from error
        return process.stdout

    def _paths_from_status_output(self, status_output: str) -> list[str]:
        changed_paths: list[str] = []
        for line in status_output.splitlines():
            if len(line) < 4:
                continue
            path_text: str = line[3:]
            if " -> " in path_text:
                path_text = path_text.split(" -> ", maxsplit=1)[1]
            normalized_path: str = Path(path_text).as_posix()
            if normalized_path == ".sgm" or normalized_path.startswith(".sgm/"):
                continue
            changed_paths.append(normalized_path)
        return changed_paths
