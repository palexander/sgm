from __future__ import annotations

from dataclasses import dataclass

from sgm.adapters.decision_loader import load_decision_document
from sgm.adapters.filesystem import FileSystemAdapter
from sgm.adapters.repository import GraphRepository
from sgm.adapters.spec_loader import load_spec_document
from sgm.adapters.system import SystemAdapter
from sgm.domain.models import RepoContext, SyncDecisionResult, SyncFilesResult, SyncSpecResult
from sgm.domain.paths import normalize_scan_root, to_repo_relative_posix


@dataclass(slots=True)
class RefreshService:
    repo_context: RepoContext
    graph_repository: GraphRepository
    filesystem: FileSystemAdapter
    system: SystemAdapter

    def refresh(self) -> None:
        repo_inventory = self.system.repo_file_inventory(self.repo_context.root)
        self.graph_repository.sync_files(
            ".",
            self.filesystem.inventory_nodes(repo_inventory),
        )
        spec_paths: tuple[str, ...] = self.filesystem.list_spec_files()
        for spec_path in spec_paths:
            spec = load_spec_document(
                self.repo_context.root / spec_path,
                self.repo_context.root,
            )
            self.graph_repository.sync_spec(spec)
        self.graph_repository.prune_specs(spec_paths)

        decision_paths: tuple[str, ...] = self.filesystem.list_decision_files()
        for decision_path in decision_paths:
            decision = load_decision_document(
                self.repo_context.root / decision_path,
                self.repo_context.root,
            )
            self.graph_repository.sync_decision(decision)
        self.graph_repository.prune_decisions(decision_paths)
        self.graph_repository.assert_unique_active_ownership()

    def sync_files(self, scan_root: str | None) -> SyncFilesResult:
        normalized_root: str = normalize_scan_root(self.repo_context.root, scan_root)
        nodes = self.filesystem.scan(normalized_root)
        return self.graph_repository.sync_files(normalized_root, nodes)

    def sync_spec(self, yaml_path: str) -> SyncSpecResult:
        normalized_path: str = to_repo_relative_posix(self.repo_context.root, yaml_path)
        spec = load_spec_document(
            self.repo_context.root / normalized_path,
            self.repo_context.root,
        )
        return self.graph_repository.sync_spec(spec)

    def sync_decision(self, yaml_path: str) -> SyncDecisionResult:
        normalized_path: str = to_repo_relative_posix(self.repo_context.root, yaml_path)
        decision = load_decision_document(
            self.repo_context.root / normalized_path,
            self.repo_context.root,
        )
        return self.graph_repository.sync_decision(decision)
