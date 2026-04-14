from __future__ import annotations

import json
import importlib.util
import sys
from pathlib import Path

from tests.integration.helpers import create_sample_repo, run_cli


def _load_hook_common_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "integrations"
        / "claude-hooks"
        / "bin"
        / "_common.py"
    )
    spec = importlib.util.spec_from_file_location("sgm_hook_common", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_validate_returns_exit_2_for_ungoverned_change(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)
    rogue_file = sample_repo.root / "src" / "middleware" / "rogue.ts"
    rogue_file.write_text("export const rogue = (): string => 'x';\n", encoding="utf-8")

    result = run_cli(
        sgm_executable,
        sample_repo.root,
        "validate",
    )

    assert result.returncode == 2
    assert "[FAIL]" in result.stdout
    assert "src/middleware/rogue.ts" in result.stdout


def test_context_returns_infra_error_for_missing_spec_file(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)

    result = run_cli(
        sgm_executable,
        sample_repo.root,
        "context",
        "specs/missing.sgm.yaml",
    )

    assert result.returncode == 3
    assert "file not found" in result.stdout or "[ERROR]" in result.stdout


def test_invalid_state_returns_exit_3(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)
    state_dir = sample_repo.root / ".sgm" / "work"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text("not-json", encoding="utf-8")

    result = run_cli(
        sgm_executable,
        sample_repo.root,
        "context",
        "specs/rpc-service-pattern.sgm.yaml",
    )

    assert result.returncode == 3
    assert "[ERROR]" in result.stdout


def test_hook_context_parser_reads_editable_and_coordination_sections() -> None:
    hook_common = _load_hook_common_module()

    active_spec_id, editable_files, coordination_files = hook_common.parse_context_output(
        "\n".join(
            [
                "[TARGET]",
                "spec-001 ConnectRPC Service Pattern (priority=1)",
                "[EDITABLE] 2 files",
                "src/services/discharge.ts",
                "src/services/nested/extra.ts",
                "[COORDINATION] 1 files",
                "README.md <- spec-docs-001",
                "Only use coordination files as follow-through when this change already touches a substantive editable file.",
            ]
        )
    )

    assert active_spec_id == "spec-001"
    assert editable_files == [
        "src/services/discharge.ts",
        "src/services/nested/extra.ts",
    ]
    assert coordination_files == ["README.md"]


def test_hook_state_paths_are_persisted_relative_to_project_root(
    tmp_path: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)
    hook_common = _load_hook_common_module()
    state_path = sample_repo.root / ".sgm" / "work" / "claude-hook-state.json"

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "active_spec_id": "spec-001",
                "active_spec_path": str(
                    sample_repo.root / "specs" / "rpc-service-pattern.sgm.yaml"
                ),
                "editable_files": [
                    str(sample_repo.root / "src" / "services" / "discharge.ts"),
                    str(sample_repo.root / "src" / "services" / "nested" / "extra.ts"),
                ],
                "coordination_files": [
                    str(sample_repo.root / "src" / "middleware" / "auth.ts"),
                ],
                "dirty_since_validate": True,
                "force_override": False,
            }
        ),
        encoding="utf-8",
    )

    loaded_state = hook_common.load_state(sample_repo.root)
    assert loaded_state.active_spec_path == "specs/rpc-service-pattern.sgm.yaml"
    assert loaded_state.editable_files == [
        "src/services/discharge.ts",
        "src/services/nested/extra.ts",
    ]
    assert loaded_state.coordination_files == ["src/middleware/auth.ts"]

    hook_common.save_state(sample_repo.root, loaded_state)
    stored_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert stored_state["active_spec_path"] == "specs/rpc-service-pattern.sgm.yaml"
    assert stored_state["editable_files"] == [
        "src/services/discharge.ts",
        "src/services/nested/extra.ts",
    ]
    assert stored_state["coordination_files"] == ["src/middleware/auth.ts"]


def test_hook_file_paths_are_relative_to_repo_root_from_nested_cwd(
    tmp_path: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)
    hook_common = _load_hook_common_module()
    outside_file = tmp_path / "notes.md"
    outside_file.write_text("notes\n", encoding="utf-8")
    nested_cwd = sample_repo.root / "src" / "services"

    repo_root = hook_common.project_root({"cwd": str(nested_cwd)})

    assert repo_root == sample_repo.root.resolve()
    assert hook_common.file_paths_from_payload(
        {
            "tool_input": {
                "file_paths": [
                    str(sample_repo.root / "specs" / "rpc-service-pattern.sgm.yaml"),
                    str(outside_file),
                ]
            }
        },
        nested_cwd,
        repo_root,
    ) == [
        "specs/rpc-service-pattern.sgm.yaml",
        "../notes.md",
    ]
