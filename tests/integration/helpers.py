from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CliResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class SampleRepo:
    root: Path
    spec_path: Path
    middleware_spec_path: Path


def create_sample_repo(tmp_path: Path) -> SampleRepo:
    repo_root = tmp_path / "sample-repo"
    (repo_root / "src" / "services").mkdir(parents=True)
    (repo_root / "src" / "services" / "nested").mkdir(parents=True)
    (repo_root / "src" / "middleware").mkdir(parents=True)
    (repo_root / "decisions").mkdir(parents=True)
    (repo_root / "specs").mkdir(parents=True)
    _write(
        repo_root / "src" / "services" / "discharge.ts",
        "export const handler = (): void => {};\n",
    )
    _write(
        repo_root / "src" / "services" / "bad-handler.ts",
        "export const handler = (): string => 'bad';\n",
    )
    _write(
        repo_root / "src" / "services" / "nested" / "extra.ts",
        "export const extra = (): boolean => true;\n",
    )
    _write(
        repo_root / "src" / "middleware" / "auth.ts",
        "export const auth = (): boolean => true;\n",
    )
    spec_path = repo_root / "specs" / "rpc-service-pattern.sgm.yaml"
    _write(spec_path, _spec_yaml(version=1))
    middleware_spec_path = repo_root / "specs" / "middleware-policy.sgm.yaml"
    _write(middleware_spec_path, _middleware_spec_yaml())
    _write(repo_root / "decisions" / "move-validation-boundary.yaml", _decision_yaml())

    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "sgm@example.com"],
        cwd=repo_root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "SGM Tests"],
        cwd=repo_root,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repo_root, check=True)
    return SampleRepo(
        root=repo_root,
        spec_path=spec_path,
        middleware_spec_path=middleware_spec_path,
    )


def bump_spec_version(spec_path: Path, version: int = 2) -> None:
    _write(spec_path, _spec_yaml(version=version))


def run_cli(
    executable: Path,
    cwd: Path,
    *args: str,
) -> CliResult:
    process = subprocess.run(
        [str(executable), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    return CliResult(
        returncode=process.returncode,
        stdout=process.stdout.strip(),
        stderr=process.stderr.strip(),
    )


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _spec_yaml(version: int) -> str:
    return "\n".join(
        [
            "id: spec-001",
            'title: "ConnectRPC Service Pattern"',
            f"version: {version}",
            "status: active",
            "author: paul",
            "text: |",
            "  All changes for this spec must stay within the files governed by it:",
            (
                "  1. `sgm context specs/rpc-service-pattern.sgm.yaml` should "
                "surface the full spec context"
            ),
            (
                "  2. `sgm validate` should validate all active specs against "
                "the current repo change set"
            ),
            (
                "  3. Files outside the governed scope require an explicit "
                "proposal before they become in-scope"
            ),
            "governs:",
            '  - selector: "src/services/**"',
            "    priority: 1",
        ]
    ) + "\n"


def _decision_yaml() -> str:
    return "\n".join(
        [
            "id: dec-001",
            'title: "Move validation to middleware boundary"',
            "status: active",
            "context: |",
            "  Validation helpers are being centralized outside individual service handlers.",
            "decision: |",
            "  New middleware code should move shared request validation out of service handlers.",
            "consequences: |",
            "  Service files may stay unchanged for now;",
            "  middleware and adjacent utilities are the active focus.",
            "touches:",
            '  - selector: "src/middleware/**"',
        ]
    ) + "\n"


def _middleware_spec_yaml() -> str:
    return "\n".join(
        [
            "id: spec-002",
            'title: "Middleware Policy"',
            "version: 1",
            "status: active",
            "author: paul",
            "text: |",
            "  Middleware work is governed separately so focus drift is visible when",
            "  service work continues while middleware remains unfinished.",
            "governs:",
            '  - selector: "src/middleware/**"',
            "    priority: 1",
        ]
    ) + "\n"
