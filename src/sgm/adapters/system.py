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
        changed_paths: list[str] = []
        for line in process.stdout.splitlines():
            if len(line) < 4:
                continue
            path_text: str = line[3:]
            if " -> " in path_text:
                path_text = path_text.split(" -> ", maxsplit=1)[1]
            normalized_path: str = Path(path_text).as_posix()
            if normalized_path == ".sgm" or normalized_path.startswith(".sgm/"):
                continue
            changed_paths.append(normalized_path)
        return tuple(sorted(dict.fromkeys(changed_paths)))
