from __future__ import annotations

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from sgm import cli
from sgm.domain.proposal_models import (
    ApprovalResult,
    Proposal,
    ProposalReviewItem,
    ProposalReviewResult,
    RejectResult,
)
from tests.integration.helpers import create_sample_repo, rewrite_spec_title, run_cli


def _activate_middleware_spec(sample_repo) -> None:
    sample_repo.middleware_spec_path.write_text(
        "\n".join(
            [
                "id: spec-002",
                'title: "Middleware Policy"',
                "status: active",
                "author: paul",
                "text: |",
                "  Middleware changes should stay within middleware files.",
                "governs:",
                '  - selector: "src/middleware/**"',
                "    priority: 1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=sample_repo.root, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "activate middleware spec"],
        cwd=sample_repo.root,
        check=True,
    )


def test_cli_spec_first_flow(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)

    no_args_result = run_cli(sgm_executable, sample_repo.root)
    assert no_args_result.returncode == 0
    assert "Shared SGM CLI for humans and agents." in no_args_result.stdout
    assert "context" in no_args_result.stdout
    assert "validate" in no_args_result.stdout
    assert "propose" in no_args_result.stdout
    assert "init" in no_args_result.stdout
    assert "proposals" in no_args_result.stdout
    assert "shared" in no_args_result.stdout
    assert "spec" in no_args_result.stdout
    assert "sync" in no_args_result.stdout
    assert "Missing command" not in no_args_result.stderr

    context_result = run_cli(
        sgm_executable,
        sample_repo.root,
        "context",
        "specs/rpc-service-pattern.sgm.yaml",
    )
    assert context_result.returncode == 0
    assert "[TARGET]" in context_result.stdout
    assert "All changes for this spec must stay within the files governed by it:" in (
        context_result.stdout
    )
    assert "[EDITABLE] 3 files" in context_result.stdout
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
        "specs/rpc-service-pattern.sgm.yaml",
        "--no-record",
    )
    assert validate_pass.returncode == 0
    assert "[PASS] all 1 changed file(s) classified for spec-001" in validate_pass.stdout
    assert "src/services/discharge.ts" in validate_pass.stdout

    validate_record = run_cli(
        sgm_executable,
        sample_repo.root,
        "validate",
        "specs/rpc-service-pattern.sgm.yaml",
    )
    assert validate_record.returncode == 0
    assert (
        "[PASS] all 1 changed file(s) classified for spec-001 (recorded)"
        in validate_record.stdout
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
        "specs/rpc-service-pattern.sgm.yaml",
        "--no-record",
    )
    assert validate_fail.returncode == 2
    assert "[FAIL] 1 changed file(s) blocked for spec-001" in validate_fail.stdout
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
        sample_repo.root / ".sgm" / "persisted" / "proposals" / f"{proposal_id}.json"
    ).is_file()
    assert not (
        sample_repo.root / ".sgm" / "work" / "proposals" / f"{proposal_id}.json"
    ).exists()

    validate_warn = run_cli(
        sgm_executable,
        sample_repo.root,
        "validate",
        "specs/rpc-service-pattern.sgm.yaml",
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
    assert "[EDITABLE] 4 files" in governed_context.stdout
    assert "src/middleware/auth.ts" in governed_context.stdout
    assert "[FOCUS-WARN]" not in governed_context.stdout

    governed_context_force = run_cli(
        sgm_executable,
        sample_repo.root,
        "context",
        "specs/rpc-service-pattern.sgm.yaml",
        "--force",
    )
    assert governed_context_force.returncode == 0
    assert "[FOCUS-WARN]" not in governed_context_force.stdout

    validate_after_approve = run_cli(
        sgm_executable,
        sample_repo.root,
        "validate",
        "specs/rpc-service-pattern.sgm.yaml",
        "--no-record",
    )
    assert validate_after_approve.returncode == 0
    assert "[PASS] all 2 changed file(s) classified for spec-001" in validate_after_approve.stdout
    assert "[FOCUS-WARN]" not in validate_after_approve.stdout

    validate_after_approve_force = run_cli(
        sgm_executable,
        sample_repo.root,
        "validate",
        "specs/rpc-service-pattern.sgm.yaml",
        "--no-record",
        "--force",
    )
    assert validate_after_approve_force.returncode == 0
    assert "[FOCUS-WARN]" not in validate_after_approve_force.stdout

    assert (
        sample_repo.root / ".sgm" / "persisted" / "proposals" / f"{proposal_id}.json"
    ).is_file()
    assert tuple((sample_repo.root / ".sgm" / "work" / "validations").rglob("*.json"))

    subprocess.run(["git", "add", "."], cwd=sample_repo.root, check=True)
    subprocess.run(["git", "commit", "-qm", "governed changes"], cwd=sample_repo.root, check=True)

    rewrite_spec_title(sample_repo.spec_path, "ConnectRPC Service Pattern Revised")
    context_with_delta = run_cli(
        sgm_executable,
        sample_repo.root,
        "context",
        "specs/rpc-service-pattern.sgm.yaml",
    )
    assert "[SPEC-DELTA] spec-001 specs/rpc-service-pattern.sgm.yaml changed since last ingest" in (
        context_with_delta.stdout
    )
    assert "[DELTA-SUMMARY]" in context_with_delta.stdout
    assert "[CLEANUP]" not in context_with_delta.stdout
    assert "--- a/specs/rpc-service-pattern.sgm.yaml" in context_with_delta.stdout
    assert "+++ b/specs/rpc-service-pattern.sgm.yaml" in context_with_delta.stdout
    assert '-title: "ConnectRPC Service Pattern"' in context_with_delta.stdout
    assert '+title: "ConnectRPC Service Pattern Revised"' in context_with_delta.stdout

    rewrite_spec_title(sample_repo.spec_path, "ConnectRPC Service Pattern Refined")
    validate_with_delta = run_cli(
        sgm_executable,
        sample_repo.root,
        "validate",
        "specs/rpc-service-pattern.sgm.yaml",
        "--no-record",
    )
    assert validate_with_delta.returncode == 0
    assert "[PASS] all 1 changed file(s) classified for spec-001" in validate_with_delta.stdout
    assert "[SPEC-DELTA] spec-001 specs/rpc-service-pattern.sgm.yaml changed since last ingest" in (
        validate_with_delta.stdout
    )
    assert "[DELTA-SUMMARY]" in validate_with_delta.stdout
    assert "[CLEANUP]" not in validate_with_delta.stdout
    assert '-title: "ConnectRPC Service Pattern Revised"' in validate_with_delta.stdout
    assert '+title: "ConnectRPC Service Pattern Refined"' in validate_with_delta.stdout

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

    spec_lines = sample_repo.spec_path.read_text(encoding="utf-8").splitlines()
    sample_repo.spec_path.write_text(
        "\n".join(
            line
            for line in spec_lines
            if line
            != (
                "  3. Files outside the governed scope require an explicit "
                "proposal before they become in-scope"
            )
        )
        + "\n",
        encoding="utf-8",
    )

    context_with_cleanup = run_cli(
        sgm_executable,
        sample_repo.root,
        "context",
        "specs/rpc-service-pattern.sgm.yaml",
    )
    assert context_with_cleanup.returncode == 0
    assert "[DELTA-SUMMARY]" in context_with_cleanup.stdout
    assert "[CLEANUP] This spec removed behavior." in context_with_cleanup.stdout

    assert tuple((sample_repo.root / ".sgm" / "work" / "validations").rglob("*.json"))


def test_spec_add_creates_template_and_opens_editor(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)
    editor_log = sample_repo.root / "editor.log"
    editor_script = sample_repo.root / "fake-editor.sh"
    editor_script.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                f"printf '%s\\n' \"$1\" > {editor_log}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    editor_script.chmod(0o755)

    env = os.environ.copy()
    env["VISUAL"] = str(editor_script)
    env.pop("EDITOR", None)

    result = subprocess.run(
        [str(sgm_executable), "spec", "add"],
        cwd=sample_repo.root,
        input="  New Command Model  \n",
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    created_spec = sample_repo.root / "specs" / "new-command-model.sgm.yaml"
    assert result.returncode == 0
    assert "[CREATED] specs/new-command-model.sgm.yaml" in result.stdout
    assert created_spec.is_file()
    assert editor_log.read_text(encoding="utf-8").strip() == str(created_spec)
    created_text = created_spec.read_text(encoding="utf-8")
    assert "id: spec-new-command-model-001" in created_text
    assert 'title: "New Command Model"' in created_text
    assert "version:" not in created_text
    assert "status: active" in created_text
    assert "author: TODO" in created_text
    assert "governs: []" in created_text


def test_spec_add_refuses_to_overwrite_existing_file(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)
    existing_spec = sample_repo.root / "specs" / "existing-spec.sgm.yaml"
    existing_spec.write_text("id: existing\n", encoding="utf-8")

    env = os.environ.copy()
    env["VISUAL"] = "true"
    env.pop("EDITOR", None)

    result = subprocess.run(
        [str(sgm_executable), "spec", "add"],
        cwd=sample_repo.root,
        input="Existing Spec\n",
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert result.returncode == 3
    assert "[ERROR] spec file already exists: specs/existing-spec.sgm.yaml" in result.stdout
    assert existing_spec.read_text(encoding="utf-8") == "id: existing\n"


def test_propose_skips_when_matching_pending_proposal_already_exists(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)
    auth_path = sample_repo.root / "src" / "middleware" / "auth.ts"
    auth_path.write_text("export const auth = (): string => 'pending';\n", encoding="utf-8")

    first_result = run_cli(
        sgm_executable,
        sample_repo.root,
        "propose",
        "spec-001",
        "src/middleware/auth.ts",
        "Auth middleware should follow service constraints",
    )
    assert first_result.returncode == 0
    proposal_id = first_result.stdout.splitlines()[0].split()[1]

    second_result = run_cli(
        sgm_executable,
        sample_repo.root,
        "propose",
        "spec-001",
        "src/middleware/auth.ts",
        "Duplicate request should reuse the pending proposal",
    )

    assert second_result.returncode == 0
    assert (
        f"[SKIP] src/middleware/auth.ts already pending under {proposal_id} for spec-001"
        in second_result.stdout
    )
    assert len(tuple((sample_repo.root / ".sgm" / "persisted" / "proposals").glob("*.json"))) == 1


def test_parallel_propose_creates_only_one_pending_record_per_target(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)
    auth_path = sample_repo.root / "src" / "middleware" / "auth.ts"
    auth_path.write_text("export const auth = (): string => 'pending';\n", encoding="utf-8")

    def run_duplicate_propose(attempt: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(sgm_executable),
                "propose",
                "spec-001",
                "src/middleware/auth.ts",
                f"Parallel repro {attempt}",
            ],
            cwd=sample_repo.root,
            text=True,
            capture_output=True,
            check=False,
        )

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(run_duplicate_propose, range(6)))

    created_results = [result for result in results if "[PROPOSED]" in result.stdout]
    skipped_results = [result for result in results if "[SKIP]" in result.stdout]

    assert len(created_results) == 1
    assert len(skipped_results) == 5
    assert all(result.returncode == 0 for result in results)
    assert len(tuple((sample_repo.root / ".sgm" / "persisted" / "proposals").glob("*.json"))) == 1


def test_propose_blocks_for_files_owned_by_another_active_spec(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)
    _activate_middleware_spec(sample_repo)

    result = run_cli(
        sgm_executable,
        sample_repo.root,
        "propose",
        "spec-001",
        "src/middleware/auth.ts",
        "Need auth middleware under the service spec",
    )

    assert result.returncode == 0
    assert "[BLOCKED] src/middleware/auth.ts is already owned by spec-002 Middleware Policy" in (
        result.stdout
    )
    assert "sgm shared allow spec-002 spec-001 src/middleware/auth.ts" in result.stdout
    assert not tuple((sample_repo.root / ".sgm" / "persisted" / "proposals").glob("*.json"))


def test_shared_allow_surfaces_owner_context_and_validate_passes(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)
    _activate_middleware_spec(sample_repo)

    allow_result = run_cli(
        sgm_executable,
        sample_repo.root,
        "shared",
        "allow",
        "spec-002",
        "spec-001",
        "src/middleware/auth.ts",
        "Shared auth work",
    )
    assert allow_result.returncode == 0
    assert "[ALLOWED] delegation-" in allow_result.stdout
    assert "ownership: unchanged" in allow_result.stdout
    assert tuple((sample_repo.root / ".sgm" / "persisted" / "delegations").glob("*.json"))

    list_result = run_cli(
        sgm_executable,
        sample_repo.root,
        "shared",
        "list",
        "specs/rpc-service-pattern.sgm.yaml",
    )
    assert "[DELEGATED-TO-THIS-SPEC] 1" in list_result.stdout
    assert "src/middleware/auth.ts <- spec-002" in list_result.stdout

    context_result = run_cli(
        sgm_executable,
        sample_repo.root,
        "context",
        "specs/rpc-service-pattern.sgm.yaml",
        "--force",
    )
    assert "[READ] 2 specs" in context_result.stdout
    assert "spec-002 [owner for src/middleware/auth.ts]" in context_result.stdout
    assert "If it disagrees, the owner wins." in context_result.stdout
    assert "[EDITABLE] 4 files" in context_result.stdout
    assert "src/middleware/auth.ts" in context_result.stdout

    auth_path = sample_repo.root / "src" / "middleware" / "auth.ts"
    auth_path.write_text("export const auth = (): string => 'shared';\n", encoding="utf-8")

    validate_result = run_cli(
        sgm_executable,
        sample_repo.root,
        "validate",
        "specs/rpc-service-pattern.sgm.yaml",
        "--no-record",
    )
    assert validate_result.returncode == 0
    assert "[PASS] all 1 changed file(s) classified for spec-001" in validate_result.stdout
    assert "src/middleware/auth.ts" in validate_result.stdout
    assert "[FOCUS-WARN]" not in validate_result.stdout


def test_coordination_files_require_substantive_edit(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)
    _activate_middleware_spec(sample_repo)

    mark_result = run_cli(
        sgm_executable,
        sample_repo.root,
        "shared",
        "mark-coordination",
        "spec-002",
        "src/middleware/auth.ts",
        "Wiring spillover",
    )
    assert mark_result.returncode == 0
    assert "[COORDINATION] coordination-" in mark_result.stdout
    assert tuple((sample_repo.root / ".sgm" / "persisted" / "coordination").glob("*.json"))

    context_result = run_cli(
        sgm_executable,
        sample_repo.root,
        "context",
        "specs/rpc-service-pattern.sgm.yaml",
        "--force",
    )
    assert "[COORDINATION] 1 files" in context_result.stdout
    assert "src/middleware/auth.ts <- spec-002" in context_result.stdout

    auth_path = sample_repo.root / "src" / "middleware" / "auth.ts"
    auth_path.write_text("export const auth = (): string => 'coord';\n", encoding="utf-8")

    validate_only_coordination = run_cli(
        sgm_executable,
        sample_repo.root,
        "validate",
        "specs/rpc-service-pattern.sgm.yaml",
        "--no-record",
    )
    assert validate_only_coordination.returncode == 2
    assert "coordination files are only allowed alongside a substantive editable change" in (
        validate_only_coordination.stdout
    )

    discharge_path = sample_repo.root / "src" / "services" / "discharge.ts"
    discharge_path.write_text(
        "export const handler = (): string => 'updated';\n",
        encoding="utf-8",
    )

    validate_with_substantive = run_cli(
        sgm_executable,
        sample_repo.root,
        "validate",
        "specs/rpc-service-pattern.sgm.yaml",
        "--no-record",
    )
    assert validate_with_substantive.returncode == 0
    assert "[NOTES]" in validate_with_substantive.stdout
    assert "coordination spillover allowed because this change also touches a substantive editable file" in (
        validate_with_substantive.stdout
    )
    assert "[FOCUS-WARN]" not in validate_with_substantive.stdout


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
    assert "[EDITABLE] 3 files" in context_result.stdout


def test_proposals_review_walks_pending_items_in_order(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)
    audit_path = sample_repo.root / "src" / "middleware" / "audit.ts"
    audit_path.write_text("export const audit = (): boolean => true;\n", encoding="utf-8")
    session_dir = sample_repo.root / "src" / "utils"
    session_dir.mkdir(parents=True)
    session_path = session_dir / "session.ts"
    session_path.write_text("export const session = (): boolean => true;\n", encoding="utf-8")

    auth_proposal = run_cli(
        sgm_executable,
        sample_repo.root,
        "propose",
        "spec-001",
        "src/middleware/auth.ts",
        "Auth middleware should follow the service spec",
    )
    audit_proposal = run_cli(
        sgm_executable,
        sample_repo.root,
        "propose",
        "spec-001",
        "src/middleware/audit.ts",
        "Audit middleware should stay with service governance",
    )
    session_proposal = run_cli(
        sgm_executable,
        sample_repo.root,
        "propose",
        "spec-001",
        "src/utils/session.ts",
        "Session helpers should stay with service governance",
    )
    assert auth_proposal.returncode == 0
    assert audit_proposal.returncode == 0
    assert session_proposal.returncode == 0

    pending_before_review = run_cli(
        sgm_executable,
        sample_repo.root,
        "proposals",
        "list",
        "--status",
        "pending",
    )
    ordered_ids = tuple(
        line.split()[0]
        for line in pending_before_review.stdout.splitlines()
        if line.startswith("prop-")
    )
    assert len(ordered_ids) == 3
    skipped_id, rejected_id, approved_id = ordered_ids

    review_result = subprocess.run(
        [str(sgm_executable), "proposals", "review"],
        cwd=sample_repo.root,
        input="?\ng\ns\nr too broad\na\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert review_result.returncode == 0
    assert "[REVIEW] 3 pending proposals" in review_result.stdout
    assert "\x1b[" not in review_result.stdout
    assert review_result.stdout.index(skipped_id) < review_result.stdout.index(rejected_id)
    assert review_result.stdout.index(rejected_id) < review_result.stdout.index(approved_id)
    assert "[HELP] a=approve r[ reason]=reject s=skip g=files q=quit ?=help" in (
        review_result.stdout
    )
    assert "[FILES] 3 governed" in review_result.stdout
    assert f"[SKIP] {skipped_id}" in review_result.stdout
    assert f"[REJECTED] {rejected_id}" in review_result.stdout
    assert "reason: too broad" in review_result.stdout
    assert f"[APPROVED] {approved_id}" in review_result.stdout
    assert "All changes for this spec must stay within the files governed by it:" in (
        review_result.stdout
    )

    pending_list = run_cli(
        sgm_executable,
        sample_repo.root,
        "proposals",
        "list",
        "--status",
        "pending",
    )
    assert skipped_id in pending_list.stdout
    assert rejected_id not in pending_list.stdout
    assert approved_id not in pending_list.stdout

    rejected_list = run_cli(
        sgm_executable,
        sample_repo.root,
        "proposals",
        "list",
        "--status",
        "rejected",
    )
    assert rejected_id in rejected_list.stdout
    assert "review_reason: too broad" in rejected_list.stdout

    approved_list = run_cli(
        sgm_executable,
        sample_repo.root,
        "proposals",
        "list",
        "--status",
        "approved",
    )
    assert approved_id in approved_list.stdout


def test_proposals_review_clears_and_redraws_in_tty(
    monkeypatch,
) -> None:
    proposal = Proposal(
        id="prop-tty",
        spec_id="spec-001",
        path="src/middleware/auth.ts",
        reason="Auth middleware should follow the service spec",
        status="pending",
        created_at=datetime(2026, 3, 28, tzinfo=UTC),
        reviewed_at=None,
        review_reason=None,
    )
    review_item = ProposalReviewItem(
        proposal=proposal,
        spec_title="Service Spec",
        spec_text="Line one\nLine two",
        governed_files=("src/middleware/auth.ts", "src/services/discharge.ts"),
    )

    class _TTYStream:
        def isatty(self) -> bool:
            return True

    class _FakeService:
        def __init__(self) -> None:
            self.approved: list[str] = []

        def proposals_review(self) -> ProposalReviewResult:
            return ProposalReviewResult(proposals=(review_item,))

        def proposals_approve(self, proposal_id: str) -> ApprovalResult:
            self.approved.append(proposal_id)
            return ApprovalResult(
                proposal_id=proposal_id,
                spec_id=proposal.spec_id,
                path=proposal.path,
            )

        def proposals_reject(self, proposal_id: str, review_reason: str | None) -> RejectResult:
            raise AssertionError("reject path should not be used in this test")

    captured: list[str] = []
    key_presses = iter(["g", "a"])

    monkeypatch.setattr(cli.sys, "stdin", _TTYStream())
    monkeypatch.setattr(cli.sys, "stdout", _TTYStream())
    monkeypatch.setattr(cli.click, "clear", lambda: captured.append("<clear>"))
    monkeypatch.setattr(cli.click, "getchar", lambda: next(key_presses))
    monkeypatch.setattr(
        cli.typer,
        "echo",
        lambda message="", nl=True: captured.append(message),
    )

    exit_code = cli._proposals_review(_FakeService())

    assert exit_code == 0
    assert captured.count("<clear>") == 2
    assert captured[0] == "<clear>"
    output = "\n".join(captured)
    assert "[REVIEW] 1/1 pending proposals" in output
    assert "[FILES] 2 governed" in output
    assert "[APPROVED] prop-tty" in output
    assert "Action [a/r/s/g/q/?]: " in output


def test_proposals_review_caps_spec_excerpt_to_terminal_height(
    monkeypatch,
) -> None:
    proposal = Proposal(
        id="prop-height",
        spec_id="spec-001",
        path="src/middleware/auth.ts",
        reason="Auth middleware should follow the service spec",
        status="pending",
        created_at=datetime(2026, 3, 28, tzinfo=UTC),
        reviewed_at=None,
        review_reason=None,
    )
    spec_text = "\n".join(
        [
            "Line one",
            "Line two",
            "Line three",
            "Line four",
            "Line five",
            "Line six",
            "Line seven",
        ]
    )
    review_item = ProposalReviewItem(
        proposal=proposal,
        spec_title="Service Spec",
        spec_text=spec_text,
        governed_files=("src/middleware/auth.ts",),
    )

    class _TTYStream:
        def isatty(self) -> bool:
            return True

    class _FakeService:
        def proposals_review(self) -> ProposalReviewResult:
            return ProposalReviewResult(proposals=(review_item,))

        def proposals_approve(self, proposal_id: str) -> ApprovalResult:
            return ApprovalResult(
                proposal_id=proposal_id,
                spec_id=proposal.spec_id,
                path=proposal.path,
            )

        def proposals_reject(self, proposal_id: str, review_reason: str | None) -> RejectResult:
            raise AssertionError("reject path should not be used in this test")

    captured: list[str] = []
    key_presses = iter(["a"])

    monkeypatch.setattr(cli.sys, "stdin", _TTYStream())
    monkeypatch.setattr(cli.sys, "stdout", _TTYStream())
    monkeypatch.setattr(cli.click, "clear", lambda: captured.append("<clear>"))
    monkeypatch.setattr(cli.click, "getchar", lambda: next(key_presses))
    monkeypatch.setattr(
        cli.shutil,
        "get_terminal_size",
        lambda fallback=(80, 24): os.terminal_size((80, 12)),
    )
    monkeypatch.setattr(
        cli.typer,
        "echo",
        lambda message="", nl=True: captured.append(message),
    )

    exit_code = cli._proposals_review(_FakeService())

    assert exit_code == 0
    output = "\n".join(captured)
    assert captured.count("<clear>") == 1
    assert "[REVIEW] 1/1 pending proposals" in output
    assert "[spec excerpt truncated]" in output
    assert "\n\n  spec summary:" in output
    assert "\n\n  keys: a=approve r[ reason]=reject s=skip g=files q=quit ?=help" in output


def test_context_uses_git_diff_when_no_local_spec_snapshot_exists(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)

    rewrite_spec_title(sample_repo.spec_path, "ConnectRPC Service Pattern Revised")

    context_result = run_cli(
        sgm_executable,
        sample_repo.root,
        "context",
        "specs/rpc-service-pattern.sgm.yaml",
        "--force",
    )

    assert context_result.returncode == 0
    assert "[SPEC-DELTA] spec-001 specs/rpc-service-pattern.sgm.yaml changed since last ingest" in (
        context_result.stdout
    )
    assert "--- a/specs/rpc-service-pattern.sgm.yaml" in context_result.stdout
    assert "+++ b/specs/rpc-service-pattern.sgm.yaml" in context_result.stdout
    assert '-title: "ConnectRPC Service Pattern"' in context_result.stdout
    assert '+title: "ConnectRPC Service Pattern Revised"' in context_result.stdout


def test_spec_targeted_commands_warn_about_other_unfinished_spec_work(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    sample_repo = create_sample_repo(tmp_path)
    middleware_spec_path = sample_repo.middleware_spec_path
    middleware_spec_path.write_text(
        "\n".join(
            [
                "id: spec-002",
                'title: "Middleware Pattern"',
                "status: active",
                "author: paul",
                "text: |",
                "  Middleware changes should stay within middleware files.",
                "governs:",
                '  - selector: "src/middleware/**"',
                "    priority: 1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=sample_repo.root, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "add middleware spec"],
        cwd=sample_repo.root,
        check=True,
    )

    auth_path = sample_repo.root / "src" / "middleware" / "auth.ts"
    auth_path.write_text(
        "export const auth = (): string => 'reviewed';\n",
        encoding="utf-8",
    )

    context_result = run_cli(
        sgm_executable,
        sample_repo.root,
        "context",
        "specs/rpc-service-pattern.sgm.yaml",
    )
    assert context_result.returncode == 0
    assert "[FOCUS-WARN]" in context_result.stdout
    assert "spec-002 specs/middleware-policy.sgm.yaml" in context_result.stdout
    assert "pending: src/middleware/auth.ts" in context_result.stdout
    assert "Use --force to continue anyway." in context_result.stdout

    forced_context = run_cli(
        sgm_executable,
        sample_repo.root,
        "context",
        "specs/rpc-service-pattern.sgm.yaml",
        "--force",
    )
    assert forced_context.returncode == 0
    assert "[FOCUS-WARN]" not in forced_context.stdout

    validate_result = run_cli(
        sgm_executable,
        sample_repo.root,
        "validate",
        "specs/rpc-service-pattern.sgm.yaml",
        "--no-record",
    )
    assert validate_result.returncode == 2
    assert "[FOCUS-WARN]" in validate_result.stdout
    assert "spec-002 specs/middleware-policy.sgm.yaml" in validate_result.stdout
    assert "src/middleware/auth.ts" in validate_result.stdout

    forced_validate = run_cli(
        sgm_executable,
        sample_repo.root,
        "validate",
        "specs/rpc-service-pattern.sgm.yaml",
        "--no-record",
        "--force",
    )
    assert forced_validate.returncode == 2
    assert "[FOCUS-WARN]" not in forced_validate.stdout
