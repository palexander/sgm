from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sgm.domain.errors import FileNotFoundOnDiskError
from sgm.domain.models import CodeNode, CodeNodeKind
from sgm.domain.paths import to_repo_relative_posix


@dataclass(frozen=True, slots=True)
class FileSystemAdapter:
    repo_root: Path

    def read_text(self, relative_path: str) -> str:
        target_path: Path = self.repo_root / relative_path
        if not target_path.is_file():
            raise FileNotFoundOnDiskError(f"file not found: {relative_path}")
        return target_path.read_text(encoding="utf-8")

    def scan(self, raw_root: str) -> tuple[CodeNode, ...]:
        root_path: Path = self.repo_root / raw_root
        if not root_path.exists():
            return ()

        paths: list[Path] = [root_path]
        paths.extend(sorted(path for path in root_path.rglob("*")))
        nodes: list[CodeNode] = []
        for path in paths:
            relative_parts: tuple[str, ...] = path.relative_to(root_path).parts
            if path != root_path and any(part.startswith(".") for part in relative_parts):
                continue
            if "__pycache__" in relative_parts or path.suffix == ".pyc":
                continue
            if path.is_symlink():
                continue
            kind: CodeNodeKind
            if path.is_dir():
                kind = "directory"
            elif path.is_file():
                kind = "file"
            else:
                continue
            repo_relative_path: str = (
                "."
                if path == self.repo_root
                else to_repo_relative_posix(self.repo_root, str(path))
            )
            stat_result = path.stat()
            nodes.append(
                CodeNode(
                    id=repo_relative_path,
                    path=repo_relative_path,
                    kind=kind,
                    name=path.name,
                    last_modified=datetime.fromtimestamp(stat_result.st_mtime),
                )
            )
        nodes.sort(key=lambda node: node.path)
        return tuple(nodes)

    def list_spec_files(self) -> tuple[str, ...]:
        specs_root: Path = self.repo_root / "specs"
        if not specs_root.is_dir():
            return ()

        spec_paths: list[str] = []
        for path in sorted(specs_root.rglob("*")):
            if not path.is_file():
                continue
            if not (
                path.name.endswith(".sgm.yaml")
                or path.name.endswith(".sgm.yml")
            ):
                continue
            spec_paths.append(to_repo_relative_posix(self.repo_root, str(path)))
        return tuple(spec_paths)

    def list_decision_files(self) -> tuple[str, ...]:
        decisions_root: Path = self.repo_root / "decisions"
        if not decisions_root.is_dir():
            return ()

        decision_paths: list[str] = []
        for path in sorted(decisions_root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix not in {".yaml", ".yml"}:
                continue
            decision_paths.append(to_repo_relative_posix(self.repo_root, str(path)))
        return tuple(decision_paths)

    def ensure_directory(self, relative_path: str) -> bool:
        target_path = self.repo_root / relative_path
        if target_path.is_dir():
            return False
        target_path.mkdir(parents=True, exist_ok=True)
        return True

    def file_exists(self, relative_path: str) -> bool:
        return (self.repo_root / relative_path).exists()

    def read_optional_text(self, relative_path: str) -> str | None:
        target_path = self.repo_root / relative_path
        if not target_path.is_file():
            return None
        return target_path.read_text(encoding="utf-8")

    def write_text(self, relative_path: str, content: str) -> None:
        target_path = self.repo_root / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
