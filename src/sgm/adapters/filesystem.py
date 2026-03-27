from __future__ import annotations

import os
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

        nodes: list[CodeNode] = []
        for path in self._scan_paths(root_path):
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

    def inventory_nodes(self, file_paths: tuple[str, ...]) -> tuple[CodeNode, ...]:
        node_paths: set[str] = {"."}
        for file_path in file_paths:
            target_path = self.repo_root / file_path
            if not target_path.is_file():
                continue
            if not self._should_include_inventory_path(target_path):
                continue
            relative_path = Path(file_path).as_posix()
            node_paths.add(relative_path)
            parent = Path(relative_path).parent
            while str(parent) != ".":
                node_paths.add(parent.as_posix())
                parent = parent.parent

        nodes: list[CodeNode] = []
        for node_path in sorted(node_paths):
            path = self.repo_root if node_path == "." else self.repo_root / node_path
            if not path.exists():
                continue
            kind: CodeNodeKind = "directory" if path.is_dir() else "file"
            stat_result = path.stat()
            nodes.append(
                CodeNode(
                    id=node_path,
                    path=node_path,
                    kind=kind,
                    name=path.name,
                    last_modified=datetime.fromtimestamp(stat_result.st_mtime),
                )
            )
        return tuple(nodes)

    def _should_include_inventory_path(self, path: Path) -> bool:
        relative_parts: tuple[str, ...] = path.relative_to(self.repo_root).parts
        if "node_modules" in relative_parts:
            return False
        if "__pycache__" in relative_parts or path.suffix == ".pyc":
            return False
        if any(part == ".sgm" for part in relative_parts):
            return False
        return not self._is_nested_repo_path(path)

    def _is_nested_repo_path(self, path: Path) -> bool:
        current = path.parent
        while current != self.repo_root:
            if (current / ".git").exists():
                return True
            current = current.parent
        return False

    def _scan_paths(self, root_path: Path) -> tuple[Path, ...]:
        paths: list[Path] = [root_path]
        if root_path != self.repo_root and not self._should_descend(root_path):
            return tuple(paths)
        for dirpath, dirnames, filenames in os.walk(root_path, topdown=True, followlinks=False):
            current_dir = Path(dirpath)
            dirnames[:] = [
                name
                for name in sorted(dirnames)
                if self._should_descend(current_dir / name)
            ]
            for dirname in dirnames:
                paths.append(current_dir / dirname)
            for filename in sorted(filenames):
                paths.append(current_dir / filename)
        return tuple(paths)

    def _should_descend(self, candidate: Path) -> bool:
        if candidate.name == "node_modules":
            return False
        if candidate.is_symlink():
            return False
        if candidate.name.startswith(".") and candidate != self.repo_root:
            return False
        return not (candidate != self.repo_root and (candidate / ".git").exists())

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
