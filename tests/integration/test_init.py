from __future__ import annotations

import subprocess
from pathlib import Path

from tests.integration.helpers import run_cli

MODULARITY_GUIDANCE = (
    "Prefer modules that align with a single spec concern so "
    "per-spec work and commits stay coherent."
)
SPEC_SELECTION_GUIDANCE = (
    "Use the narrower behavior spec that matches the work: command model, "
    "context and delta, validation and focus, persistence, init, or spec format."
)


def test_init_bootstraps_repo_without_claude(tmp_path: Path, sgm_executable: Path) -> None:
    repo_root = tmp_path / "init-repo"
    repo_root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)

    result = run_cli(sgm_executable, repo_root, "init")

    assert result.returncode == 0
    assert "[INIT] sgm workspace prepared" in result.stdout
    assert "directories:" in result.stdout
    assert "created: .gitignore, AGENTS.md" in result.stdout
    assert "codex/gemini:" in result.stdout
    assert (repo_root / "specs").is_dir()
    assert (repo_root / "decisions").is_dir()
    assert (repo_root / ".sgm" / "work").is_dir()
    assert (repo_root / ".sgm" / "persisted").is_dir()
    gitignore_text = (repo_root / ".gitignore").read_text(encoding="utf-8")
    assert "__pycache__/" in gitignore_text
    assert "*.pyc" in gitignore_text
    assert ".sgm/work/" in gitignore_text
    assert ".sgm/persisted/validations/" in gitignore_text
    assert "sgm-state/" in gitignore_text
    agents_text = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    assert (
        "Main agent: orchestrate spec work and hand implementation to a sub-agent."
        in agents_text
    )
    assert SPEC_SELECTION_GUIDANCE in agents_text
    assert (
        MODULARITY_GUIDANCE in agents_text
    )
    assert "Proposal records are durable immediately in `.sgm/persisted/proposals/`." in (
        agents_text
    )
    assert "sgm context <spec-file-or-id>" in agents_text
    assert "sgm validate" in agents_text
    assert "sgm persist" not in agents_text


def test_init_updates_existing_claude_md(tmp_path: Path, sgm_executable: Path) -> None:
    repo_root = tmp_path / "claude-repo"
    repo_root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    (repo_root / "CLAUDE.md").write_text("# Claude\n", encoding="utf-8")
    (repo_root / "AGENTS.md").write_text("Existing agent guidance.\n", encoding="utf-8")

    result = run_cli(sgm_executable, repo_root, "init")

    assert result.returncode == 0
    assert "updated: AGENTS.md, CLAUDE.md" in result.stdout
    assert "claude:" in result.stdout
    agents_text = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    assert "Existing agent guidance." in agents_text
    assert (
        "Main agent: orchestrate spec work and hand implementation to a sub-agent."
        in agents_text
    )
    assert SPEC_SELECTION_GUIDANCE in agents_text
    assert (
        MODULARITY_GUIDANCE in agents_text
    )
    assert "Proposal records are durable immediately in `.sgm/persisted/proposals/`." in (
        agents_text
    )
    assert "sgm validate" in agents_text
    claude_text = (repo_root / "CLAUDE.md").read_text(encoding="utf-8")
    assert "## SGM" in claude_text
    assert "sgm context <spec-file-or-id>" in claude_text
    assert "Use the narrower behavior spec that matches the work" in claude_text
    assert "- `sgm validate` after edits" in claude_text
    assert "Proposal records are durable immediately in `.sgm/persisted/proposals/`" in (
        claude_text
    )
    assert "Prefer modules that align with a single spec concern when practical" in claude_text


def test_init_rewrites_existing_agents_guidance_without_duplication(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    repo_root = tmp_path / "agents-repo"
    repo_root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    (repo_root / "AGENTS.md").write_text(
        "\n".join(
            [
                "Use `sgm` when working in governed areas.",
                "",
                f"- {MODULARITY_GUIDANCE}",
                "- Proposal records are durable immediately in `.sgm/persisted/proposals/`.",
                "- Before edits: `uv run sgm context <spec-file-or-id>`",
                "- After edits: `uv run sgm validate`",
                "- Dry run only: `uv run sgm validate --no-record`",
                (
                    '- If a touched file is ungoverned: `uv run sgm propose '
                    '<spec-id> <path> "<reason>"`'
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_cli(sgm_executable, repo_root, "init")

    assert result.returncode == 0
    assert "created: .gitignore" in result.stdout
    assert "updated: AGENTS.md" in result.stdout
    gitignore_text = (repo_root / ".gitignore").read_text(encoding="utf-8")
    assert "__pycache__/" in gitignore_text
    assert "*.pyc" in gitignore_text
    assert ".sgm/work/" in gitignore_text
    assert ".sgm/persisted/validations/" in gitignore_text
    assert "sgm-state/" in gitignore_text
    agents_text = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    assert agents_text.count("Use `sgm` when working in governed areas.") == 1
    assert (
        "Main agent: orchestrate spec work and hand implementation to a sub-agent."
        in agents_text
    )
    assert SPEC_SELECTION_GUIDANCE in agents_text
    assert (
        MODULARITY_GUIDANCE in agents_text
    )
    assert "Proposal records are durable immediately" in agents_text
    assert "`sgm context <spec-file-or-id>`" in agents_text
    assert "`sgm validate`" in agents_text
    assert "`uv run sgm context <spec-file-or-id>`" not in agents_text
    assert "`uv run sgm persist`" not in agents_text


def test_init_rewrites_stale_claude_section(tmp_path: Path, sgm_executable: Path) -> None:
    repo_root = tmp_path / "stale-claude-repo"
    repo_root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    (repo_root / "CLAUDE.md").write_text(
        "# Claude\n\n## SGM\n\nold instructions\n",
        encoding="utf-8",
    )

    result = run_cli(sgm_executable, repo_root, "init")

    assert result.returncode == 0
    assert "updated: CLAUDE.md" in result.stdout
    claude_text = (repo_root / "CLAUDE.md").read_text(encoding="utf-8")
    assert claude_text.count("## SGM") == 1
    assert "old instructions" not in claude_text
    assert "Use `sgm` before and after governed edits:" in claude_text
    assert "Use the narrower behavior spec that matches the work" in claude_text
    assert "- `sgm validate` after edits" in claude_text
    assert "Proposal records are durable immediately in `.sgm/persisted/proposals/`" in (
        claude_text
    )
    assert "Prefer modules that align with a single spec concern when practical" in claude_text
