from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from sgm.adapters.system import SystemAdapter


def test_repo_file_inventory_filters_runtime_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    fake_output = "\0".join(
        [
            ".gitignore",
            ".sgm/persisted/proposals/prop.json",
            "packages/app/node_modules/dep/index.js",
            "src/index.ts",
        ]
    )

    def fake_run(*_: object, **__: object) -> object:
        return SimpleNamespace(stdout=fake_output)

    monkeypatch.setattr(subprocess, "run", fake_run)

    inventory = SystemAdapter().repo_file_inventory(repo_root)

    assert inventory == (".gitignore", "src/index.ts")
