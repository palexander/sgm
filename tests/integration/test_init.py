from __future__ import annotations

import json
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
UNOWNED_GUIDANCE = 'If a touched file is unowned: `sgm propose <spec-id> <path> "<reason>"`.'
FOREIGN_OWNER_GUIDANCE = (
    "If another spec owns the file: ask a human, then record `sgm shared allow "
    '<owner-spec-id> <spec-id> <path> "<reason>"`.'
)
OWNER_WINS_GUIDANCE = "On delegated shared files, the owner spec wins."
COORDINATION_GUIDANCE = (
    "Coordination files are only for mechanical follow-through alongside substantive editable work."
)
HOOK_MISSING_MESSAGE = "SGM hook skipped: install the sgm binary to enable governance hooks."


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
    assert "sgm-state/" in gitignore_text
    agents_text = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    assert (
        "Main agent: orchestrate spec work and hand implementation to a sub-agent." in agents_text
    )
    assert SPEC_SELECTION_GUIDANCE in agents_text
    assert MODULARITY_GUIDANCE in agents_text
    assert "Do not edit spec files directly during implementation; use `sgm propose`" in agents_text
    assert "Proposal records are durable immediately in `.sgm/persisted/proposals/`." in (
        agents_text
    )
    assert UNOWNED_GUIDANCE in agents_text
    assert FOREIGN_OWNER_GUIDANCE in agents_text
    assert OWNER_WINS_GUIDANCE in agents_text
    assert COORDINATION_GUIDANCE in agents_text
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
        "Main agent: orchestrate spec work and hand implementation to a sub-agent." in agents_text
    )
    assert SPEC_SELECTION_GUIDANCE in agents_text
    assert MODULARITY_GUIDANCE in agents_text
    assert "Proposal records are durable immediately in `.sgm/persisted/proposals/`." in (
        agents_text
    )
    assert "sgm validate" in agents_text
    claude_text = (repo_root / "CLAUDE.md").read_text(encoding="utf-8")
    assert "## SGM" in claude_text
    assert "sgm context <spec-file-or-id>" in claude_text
    assert "Use the narrower behavior spec that matches the work" in claude_text
    assert "- `sgm validate` after edits" in claude_text
    assert '`sgm shared allow <owner-spec-id> <spec-id> <path> "<reason>"`' in claude_text
    assert "owner spec wins" in claude_text
    assert "Coordination files are only for follow-through" in claude_text
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
                    "- If a touched file is unowned: `uv run sgm propose "
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
    assert "sgm-state/" in gitignore_text
    agents_text = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    assert agents_text.count("Use `sgm` when working in governed areas.") == 1
    assert (
        "Main agent: orchestrate spec work and hand implementation to a sub-agent." in agents_text
    )
    assert SPEC_SELECTION_GUIDANCE in agents_text
    assert MODULARITY_GUIDANCE in agents_text
    assert "Do not edit spec files directly during implementation; use `sgm propose`" in agents_text
    assert "Proposal records are durable immediately" in agents_text
    assert UNOWNED_GUIDANCE in agents_text
    assert FOREIGN_OWNER_GUIDANCE in agents_text
    assert OWNER_WINS_GUIDANCE in agents_text
    assert COORDINATION_GUIDANCE in agents_text
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
    assert '`sgm shared allow <owner-spec-id> <spec-id> <path> "<reason>"`' in claude_text
    assert "owner spec wins" in claude_text
    assert "Coordination files are only for follow-through" in claude_text
    assert (
        "- Do not edit spec files directly during implementation; use `sgm propose`" in claude_text
    )
    assert "Proposal records are durable immediately in `.sgm/persisted/proposals/`" in (
        claude_text
    )
    assert "Prefer modules that align with a single spec concern when practical" in claude_text


def test_init_installs_claude_hooks(tmp_path: Path, sgm_executable: Path) -> None:
    repo_root = tmp_path / "claude-hooks-repo"
    repo_root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)

    result = run_cli(sgm_executable, repo_root, "init", "--hooks", "claude")

    assert result.returncode == 0
    assert "hooks: claude" in result.stdout
    settings = json.loads((repo_root / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert _hook_commands(settings, "PreToolUse", "Bash") == [_expected_hook_command("pretool")]
    assert _hook_commands(settings, "PreToolUse", "Edit") == [_expected_hook_command("pretool")]
    assert _hook_commands(settings, "PreToolUse", "Write") == [_expected_hook_command("pretool")]
    assert _hook_commands(settings, "PostToolUse", "Bash") == [_expected_hook_command("posttool")]
    assert _hook_commands(settings, "Stop", "") == [_expected_hook_command("stop")]
    assert _hook_commands(settings, "SubagentStop", "") == [_expected_hook_command("stop")]

    _assert_missing_sgm_hook_skips(repo_root, _expected_hook_command("pretool"))


def test_init_installs_codex_hooks_and_preserves_existing_hooks(
    tmp_path: Path,
    sgm_executable: Path,
) -> None:
    repo_root = tmp_path / "codex-hooks-repo"
    repo_root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    existing_config = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "echo existing",
                        }
                    ],
                }
            ]
        }
    }
    (repo_root / ".codex").mkdir()
    (repo_root / ".codex" / "hooks.json").write_text(
        json.dumps(existing_config),
        encoding="utf-8",
    )

    result = run_cli(sgm_executable, repo_root, "init", "--hooks", "codex")
    second_result = run_cli(sgm_executable, repo_root, "init", "--hooks", "codex")

    assert result.returncode == 0
    assert second_result.returncode == 0
    assert "hooks: codex" in result.stdout
    config = json.loads((repo_root / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    assert _hook_commands(config, "PreToolUse", "Bash") == [
        "echo existing",
        _expected_hook_command("pretool"),
    ]
    assert _hook_commands(config, "PostToolUse", "Bash") == [_expected_hook_command("posttool")]
    assert _hook_commands(config, "Stop", "") == [_expected_hook_command("stop")]
    assert _all_hook_commands(config).count(_expected_hook_command("pretool")) == 1
    assert _all_hook_commands(config).count(_expected_hook_command("posttool")) == 1
    assert _all_hook_commands(config).count(_expected_hook_command("stop")) == 1

    _assert_missing_sgm_hook_skips(repo_root, _expected_hook_command("stop"))


def test_init_installs_all_agent_hooks(tmp_path: Path, sgm_executable: Path) -> None:
    repo_root = tmp_path / "all-hooks-repo"
    repo_root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)

    result = run_cli(sgm_executable, repo_root, "init", "--hooks", "all")

    assert result.returncode == 0
    assert "hooks: claude, codex" in result.stdout
    assert (repo_root / ".claude" / "settings.json").is_file()
    assert (repo_root / ".codex" / "hooks.json").is_file()


def _hook_commands(config: dict[str, object], event: str, matcher: str) -> list[str]:
    commands: list[str] = []
    hooks = config.get("hooks")
    assert isinstance(hooks, dict)
    entries = hooks.get(event)  # type: ignore[arg-type]
    assert isinstance(entries, list)
    for entry in entries:
        assert isinstance(entry, dict)
        if entry.get("matcher", "") != matcher:
            continue
        raw_hooks = entry.get("hooks")
        assert isinstance(raw_hooks, list)
        for hook in raw_hooks:
            assert isinstance(hook, dict)
            command = hook.get("command")
            assert isinstance(command, str)
            commands.append(command)
    return commands


def _expected_hook_command(hook_name: str) -> str:
    return (
        "sh -c 'if command -v sgm >/dev/null 2>&1; then "
        f"exec sgm hook {hook_name}; "
        f'fi; printf "%s\\n" "{HOOK_MISSING_MESSAGE}" >&2; exit 0\''
    )


def _assert_missing_sgm_hook_skips(repo_root: Path, command: str) -> None:
    bin_dir = repo_root / "empty-path"
    bin_dir.mkdir()
    (bin_dir / "sh").symlink_to("/bin/sh")

    result = subprocess.run(
        command,
        cwd=repo_root,
        env={"PATH": str(bin_dir)},
        shell=True,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert HOOK_MISSING_MESSAGE in result.stderr


def _all_hook_commands(config: dict[str, object]) -> list[str]:
    commands: list[str] = []
    hooks = config.get("hooks")
    assert isinstance(hooks, dict)
    for event_entries in hooks.values():
        assert isinstance(event_entries, list)
        for entry in event_entries:
            assert isinstance(entry, dict)
            raw_hooks = entry.get("hooks")  # type: ignore[arg-type]
            assert isinstance(raw_hooks, list)
            for hook in raw_hooks:
                assert isinstance(hook, dict)
                command = hook.get("command")
                assert isinstance(command, str)
                commands.append(command)
    return commands
