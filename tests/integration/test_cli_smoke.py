from __future__ import annotations

from pathlib import Path

from tests.integration.helpers import bump_spec_version, create_sample_repo, run_cli


def test_cli_smoke_flow(
    tmp_path: Path,
    sgm_executable: Path,
    memgraph_container: tuple[str, int],
) -> None:
    host, port = memgraph_container
    sample_repo = create_sample_repo(tmp_path)

    context_result = run_cli(
        sgm_executable,
        sample_repo.root,
        host,
        port,
        "context",
        "src/services/discharge.ts",
    )
    assert context_result.returncode == 0
    assert "[SPECS] 1 governing" in context_result.stdout
    assert "[SIBLINGS] 2 other files under spec-001" in context_result.stdout

    validate_pass = run_cli(
        sgm_executable,
        sample_repo.root,
        host,
        port,
        "validate",
        "src/services/discharge.ts",
        "--no-record",
    )
    assert validate_pass.returncode == 0
    assert "[PASS] 2/2 assertions" in validate_pass.stdout

    validate_fail = run_cli(
        sgm_executable,
        sample_repo.root,
        host,
        port,
        "validate",
        "src/services/bad-handler.ts",
    )
    assert validate_fail.returncode == 2
    assert "[FAIL] 2/2" in validate_fail.stdout
    assert "(recorded)" in validate_fail.stdout
    assert "spec-001 compliance:" in validate_fail.stdout

    context_after_record = run_cli(
        sgm_executable,
        sample_repo.root,
        host,
        port,
        "context",
        "src/services/bad-handler.ts",
    )
    assert "compliance=" in context_after_record.stdout

    bump_spec_version(sample_repo.spec_path)
    context_with_delta = run_cli(
        sgm_executable,
        sample_repo.root,
        host,
        port,
        "context",
        "src/services/bad-handler.ts",
    )
    assert "[SPEC-DELTA] spec-001 specs/rpc-service-pattern.yaml changed since last ingest" in (
        context_with_delta.stdout
    )
    assert "--- a/specs/rpc-service-pattern.yaml" in context_with_delta.stdout
    assert "+++ b/specs/rpc-service-pattern.yaml" in context_with_delta.stdout
    assert "-version: 1" in context_with_delta.stdout
    assert "+version: 2" in context_with_delta.stdout

    bump_spec_version(sample_repo.spec_path, version=3)
    validate_with_delta = run_cli(
        sgm_executable,
        sample_repo.root,
        host,
        port,
        "validate",
        "src/services/bad-handler.ts",
        "--no-record",
    )
    assert "[SPEC-DELTA] spec-001 specs/rpc-service-pattern.yaml changed since last ingest" in (
        validate_with_delta.stdout
    )
    assert "-version: 2" in validate_with_delta.stdout
    assert "+version: 3" in validate_with_delta.stdout

    ungoverned_context = run_cli(
        sgm_executable,
        sample_repo.root,
        host,
        port,
        "context",
        "src/middleware/auth.ts",
    )
    assert ungoverned_context.returncode == 0
    assert ungoverned_context.stdout == "[SKIP] no governing specs"

    propose_result = run_cli(
        sgm_executable,
        sample_repo.root,
        host,
        port,
        "propose",
        "spec-001",
        "src/middleware/auth.ts",
        "Auth middleware should follow service constraints",
    )
    assert propose_result.returncode == 0
    assert "[PROPOSED] prop-" in propose_result.stdout
    proposal_id = propose_result.stdout.splitlines()[0].split()[1]

    list_result = run_cli(
        sgm_executable,
        sample_repo.root,
        host,
        port,
        "proposals",
        "list",
        "--status",
        "pending",
    )
    assert list_result.returncode == 0
    assert proposal_id in list_result.stdout

    approve_result = run_cli(
        sgm_executable,
        sample_repo.root,
        host,
        port,
        "proposals",
        "approve",
        proposal_id,
    )
    assert approve_result.returncode == 0
    assert "[APPROVED]" in approve_result.stdout

    governed_context = run_cli(
        sgm_executable,
        sample_repo.root,
        host,
        port,
        "context",
        "src/middleware/auth.ts",
    )
    assert governed_context.returncode == 0
    assert "[SPECS] 1 governing" in governed_context.stdout

    sync_files = run_cli(
        sgm_executable,
        sample_repo.root,
        host,
        port,
        "sync",
        "files",
        "--path",
        "src",
    )
    assert sync_files.returncode == 0
    assert "indexed" in sync_files.stdout

    sync_spec_v2 = run_cli(
        sgm_executable,
        sample_repo.root,
        host,
        port,
        "sync",
        "spec",
        "specs/rpc-service-pattern.yaml",
    )
    assert sync_spec_v2.returncode == 0

    context_after_bump = run_cli(
        sgm_executable,
        sample_repo.root,
        host,
        port,
        "context",
        "src/services/bad-handler.ts",
    )
    assert "[SPEC-DELTA]" not in context_after_bump.stdout
    before_line = next(
        line for line in context_after_record.stdout.splitlines() if "compliance=" in line
    )
    after_line = next(
        line for line in context_after_bump.stdout.splitlines() if "compliance=" in line
    )
    assert before_line == after_line


def test_validate_no_record_leaves_compliance_unchanged(
    tmp_path: Path,
    sgm_executable: Path,
    memgraph_container: tuple[str, int],
) -> None:
    host, port = memgraph_container
    sample_repo = create_sample_repo(tmp_path)

    dry_run = run_cli(
        sgm_executable,
        sample_repo.root,
        host,
        port,
        "validate",
        "src/services/bad-handler.ts",
        "--no-record",
    )
    assert dry_run.returncode == 2
    assert "(recorded)" not in dry_run.stdout
    assert "compliance:" not in dry_run.stdout

    context_result = run_cli(
        sgm_executable,
        sample_repo.root,
        host,
        port,
        "context",
        "src/services/bad-handler.ts",
    )
    assert "compliance=" not in context_result.stdout
