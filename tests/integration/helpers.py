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


def create_sample_repo(tmp_path: Path) -> SampleRepo:
    repo_root = tmp_path / "sample-repo"
    (repo_root / "src" / "services").mkdir(parents=True)
    (repo_root / "src" / "services" / "nested").mkdir(parents=True)
    (repo_root / "src" / "middleware").mkdir(parents=True)
    (repo_root / "src" / "proto").mkdir(parents=True)
    (repo_root / "decisions").mkdir(parents=True)
    (repo_root / "specs").mkdir(parents=True)

    _write(
        repo_root / "src" / "proto" / "discharge_pb.ts",
        "export type DischargeRequest = { id: string }\n",
    )
    _write(
        repo_root / "src" / "services" / "discharge.ts",
        "\n".join(
            [
                "import { DischargeRequest } from '../proto/discharge_pb'",
                "export const handler = (_request: DischargeRequest): void => {};",
            ]
        )
        + "\n",
    )
    _write(
        repo_root / "src" / "services" / "bad-handler.ts",
        "\n".join(
            [
                "import { sql } from 'drizzle-orm'",
                "export const handler = (): string => sql.toString();",
            ]
        )
        + "\n",
    )
    _write(
        repo_root / "src" / "services" / "nested" / "extra.ts",
        "import { DischargeRequest } from '../../proto/discharge_pb'\n",
    )
    _write(
        repo_root / "src" / "middleware" / "auth.ts",
        "export const auth = (): boolean => true;\n",
    )
    spec_path = repo_root / "specs" / "rpc-service-pattern.yaml"
    _write(spec_path, _spec_yaml(version=1))
    _write(repo_root / "decisions" / "move-validation-boundary.yaml", _decision_yaml())

    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    return SampleRepo(root=repo_root, spec_path=spec_path)


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
            "warn_below: 0.8",
            "text: |",
            "  All RPC service handlers must:",
            "  1. Accept and return Protobuf-generated types only",
            "  2. Never access the database directly",
            "assertions:",
            "  - id: assert-001",
            '    rule: "No direct database imports in service handlers"',
            '    hint: "Use a repository layer instead of DB packages."',
            "    kind: structural",
            "    severity: error",
            "    check: file-import-deny",
            "    config:",
            '      deny: ["drizzle-orm", "pg"]',
            "  - id: assert-002",
            '    rule: "Handler files must import generated proto types"',
            '    hint: "Import from generated *_pb modules."',
            "    kind: structural",
            "    severity: warning",
            "    check: file-import-require",
            "    config:",
            '      require: ["_pb"]',
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
