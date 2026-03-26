from __future__ import annotations

import subprocess
from pathlib import Path

from tests.integration.helpers import bump_spec_version, create_sample_repo, run_cli


def test_cli_spec_first_flow(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)

    context_result = run_cli(
        sgm_executable,
        sample_repo.root,
        "context",
        "specs/rpc-service-pattern.sgm.yaml",
    )
    assert context_result.returncode == 0
    assert "[SPEC] 1 governing" in context_result.stdout
    assert "All changes for this spec must stay within the files governed by it:" in (
        context_result.stdout
    )
    assert "[FILES] 3 governed" in context_result.stdout
    assert "src/services/discharge.ts" in context_result.stdout
    assert "src/services/bad-handler.ts" in context_result.stdout
    assert "src/services/nested/extra.ts" in context_result.stdout
    assert "src/middleware/auth.ts" not in context_result.stdout

    validate_clean = run_cli(
        sgm_executable,
        sample_repo.root,
        "validate",
        "--no-record",
    )
    assert validate_clean.returncode == 0
    assert "[PASS] no changed files for spec-001" in validate_clean.stdout

    discharge_path = sample_repo.root / "src" / "services" / "discharge.ts"
    discharge_path.write_text(
        "export const handler = (): string => 'updated';\n",
        encoding="utf-8",
    )

    validate_pass = run_cli(
        sgm_executable,
        sample_repo.root,
        "validate",
        "--no-record",
    )
    assert validate_pass.returncode == 0
    assert "[PASS] all 1 changed file(s) stayed within spec-001" in validate_pass.stdout
    assert "src/services/discharge.ts" in validate_pass.stdout

    validate_record = run_cli(
        sgm_executable,
        sample_repo.root,
        "validate",
    )
    assert validate_record.returncode == 0
    assert "[PASS] all 1 changed file(s) stayed within spec-001 (recorded)" in (
        validate_record.stdout
    )
    assert tuple((sample_repo.root / ".sgm" / "work" / "validations").rglob("*.json"))

    auth_path = sample_repo.root / "src" / "middleware" / "auth.ts"
    auth_path.write_text(
        "export const auth = (): string => 'pending';\n",
        encoding="utf-8",
    )

    validate_fail = run_cli(
        sgm_executable,
        sample_repo.root,
        "validate",
        "--no-record",
    )
    assert validate_fail.returncode == 2
    assert "[FAIL] 1 changed file(s) outside spec-001" in validate_fail.stdout
    assert "src/middleware/auth.ts" in validate_fail.stdout

    propose_result = run_cli(
        sgm_executable,
        sample_repo.root,
        "propose",
        "spec-001",
        "src/middleware/auth.ts",
        "Auth middleware should follow service constraints",
    )
    assert propose_result.returncode == 0
    assert "[PROPOSED] prop-" in propose_result.stdout
    proposal_id = propose_result.stdout.splitlines()[0].split()[1]
    assert (
        sample_repo.root / ".sgm" / "work" / "proposals" / f"{proposal_id}.json"
    ).is_file()

    validate_warn = run_cli(
        sgm_executable,
        sample_repo.root,
        "validate",
        "--no-record",
    )
    assert validate_warn.returncode == 1
    assert "[WARN] 1 changed file(s) pending governance for spec-001" in validate_warn.stdout
    assert proposal_id in validate_warn.stdout

    approve_result = run_cli(
        sgm_executable,
        sample_repo.root,
        "proposals",
        "approve",
        proposal_id,
    )
    assert approve_result.returncode == 0
    assert "[APPROVED]" in approve_result.stdout

    governed_context = run_cli(
        sgm_executable,
        sample_repo.root,
        "context",
        "specs/rpc-service-pattern.sgm.yaml",
    )
    assert governed_context.returncode == 0
    assert "[FILES] 4 governed" in governed_context.stdout
    assert "src/middleware/auth.ts" in governed_context.stdout

    validate_after_approve = run_cli(
        sgm_executable,
        sample_repo.root,
        "validate",
        "--no-record",
    )
    assert validate_after_approve.returncode == 0
    assert "[PASS] all 2 changed file(s) stayed within spec-001" in validate_after_approve.stdout

    persist_proposal_result = run_cli(
        sgm_executable,
        sample_repo.root,
        "persist",
    )
    assert persist_proposal_result.returncode == 0
    assert "persisted 1 proposals" in persist_proposal_result.stdout
    assert (
        sample_repo.root / ".sgm" / "persisted" / "proposals" / f"{proposal_id}.json"
    ).is_file()
    assert not (
        sample_repo.root / ".sgm" / "work" / "proposals" / f"{proposal_id}.json"
    ).exists()
    assert tuple((sample_repo.root / ".sgm" / "work" / "validations").rglob("*.json"))
    assert not tuple((sample_repo.root / ".sgm" / "persisted" / "validations").rglob("*.json"))

    subprocess.run(["git", "add", "."], cwd=sample_repo.root, check=True)
    subprocess.run(["git", "commit", "-qm", "governed changes"], cwd=sample_repo.root, check=True)

    bump_spec_version(sample_repo.spec_path)
    context_with_delta = run_cli(
        sgm_executable,
        sample_repo.root,
        "context",
        "specs/rpc-service-pattern.sgm.yaml",
    )
    assert "[SPEC-DELTA] spec-001 specs/rpc-service-pattern.sgm.yaml changed since last ingest" in (
        context_with_delta.stdout
    )
    assert "--- a/specs/rpc-service-pattern.sgm.yaml" in context_with_delta.stdout
    assert "+++ b/specs/rpc-service-pattern.sgm.yaml" in context_with_delta.stdout
    assert "-version: 1" in context_with_delta.stdout
    assert "+version: 2" in context_with_delta.stdout

    bump_spec_version(sample_repo.spec_path, version=3)
    validate_with_delta = run_cli(
        sgm_executable,
        sample_repo.root,
        "validate",
        "--no-record",
    )
    assert validate_with_delta.returncode == 0
    assert "[PASS] all 1 changed file(s) stayed within spec-001" in validate_with_delta.stdout
    assert "[SPEC-DELTA] spec-001 specs/rpc-service-pattern.sgm.yaml changed since last ingest" in (
        validate_with_delta.stdout
    )
    assert "-version: 2" in validate_with_delta.stdout
    assert "+version: 3" in validate_with_delta.stdout

    sync_decision = run_cli(
        sgm_executable,
        sample_repo.root,
        "sync",
        "decision",
        "decisions/move-validation-boundary.yaml",
    )
    assert sync_decision.returncode == 0
    assert "ingested dec-001" in sync_decision.stdout

    sync_files = run_cli(
        sgm_executable,
        sample_repo.root,
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
        "sync",
        "spec",
        "specs/rpc-service-pattern.sgm.yaml",
    )
    assert sync_spec_v2.returncode == 0

    context_after_bump = run_cli(
        sgm_executable,
        sample_repo.root,
        "context",
        "specs/rpc-service-pattern.sgm.yaml",
    )
    assert "[SPEC-DELTA]" not in context_after_bump.stdout

    persist_validation_result = run_cli(
        sgm_executable,
        sample_repo.root,
        "persist",
    )
    assert persist_validation_result.returncode == 0
    assert "persisted 0 proposals" in persist_validation_result.stdout
    assert tuple((sample_repo.root / ".sgm" / "work" / "validations").rglob("*.json"))
    assert not tuple((sample_repo.root / ".sgm" / "persisted" / "validations").rglob("*.json"))


def test_validate_no_record_leaves_recorded_state_unchanged(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)

    dry_run = run_cli(
        sgm_executable,
        sample_repo.root,
        "validate",
        "--no-record",
    )
    assert dry_run.returncode == 0
    assert "(recorded)" not in dry_run.stdout
    assert not tuple((sample_repo.root / ".sgm" / "work" / "validations").rglob("*.json"))

    context_result = run_cli(
        sgm_executable,
        sample_repo.root,
        "context",
        "specs/rpc-service-pattern.sgm.yaml",
    )
    assert "[FILES] 3 governed" in context_result.stdout
