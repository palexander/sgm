from __future__ import annotations

from pathlib import Path

from tests.integration.helpers import create_sample_repo, run_cli


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
