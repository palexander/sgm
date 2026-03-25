from __future__ import annotations

from pathlib import Path

from tests.integration.helpers import create_sample_repo, run_cli


def test_validate_returns_infra_error_for_missing_disk_file(
    tmp_path: Path,
    sgm_executable: Path,
    memgraph_container: tuple[str, int],
) -> None:
    host, port = memgraph_container
    sample_repo = create_sample_repo(tmp_path)

    result = run_cli(
        sgm_executable,
        sample_repo.root,
        host,
        port,
        "validate",
        "src/services/missing.ts",
    )

    assert result.returncode == 3
    assert "file not found" in result.stdout


def test_context_returns_not_indexed_for_missing_path(
    tmp_path: Path,
    sgm_executable: Path,
    memgraph_container: tuple[str, int],
) -> None:
    host, port = memgraph_container
    sample_repo = create_sample_repo(tmp_path)

    result = run_cli(
        sgm_executable,
        sample_repo.root,
        host,
        port,
        "context",
        "src/services/missing.ts",
    )

    assert result.returncode == 0
    assert result.stdout == "[SKIP] not indexed"


def test_graph_unreachable_returns_exit_3(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)

    result = run_cli(
        sgm_executable,
        sample_repo.root,
        "127.0.0.1",
        65530,
        "context",
        "src/services/discharge.ts",
    )

    assert result.returncode == 3
    assert "[ERROR]" in result.stdout
