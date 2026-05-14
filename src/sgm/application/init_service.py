from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from sgm.adapters.filesystem import FileSystemAdapter
from sgm.domain.models import InitOffer, InitResult

AGENTS_GUIDANCE_LINE = (
    "Prefer modules that align with a single spec concern so "
    "per-spec work and commits stay coherent."
)
SPEC_EDIT_GUIDANCE_LINE = (
    "Do not edit spec files directly during implementation; use "
    "`sgm propose` for incidental splash expansion."
)
PROPOSAL_GUIDANCE_LINE = "Proposal records are durable immediately in `.sgm/persisted/proposals/`."
UNOWNED_GUIDANCE_LINE = 'If a touched file is unowned: `sgm propose <spec-id> <path> "<reason>"`.'
FOREIGN_OWNER_GUIDANCE_LINE = (
    "If another spec owns the file: ask a human, then record "
    '`sgm shared allow <owner-spec-id> <spec-id> <path> "<reason>"`.'
)
OWNER_WINS_GUIDANCE_LINE = "On delegated shared files, the owner spec wins."
COORDINATION_GUIDANCE_LINE = (
    "Coordination files are only for mechanical follow-through alongside substantive editable work."
)
SPEC_SELECTION_GUIDANCE_LINE = (
    "Use the narrower behavior spec that matches the work: command model, "
    "context and delta, validation and focus, persistence, init, or spec format."
)
HOOK_MISSING_MESSAGE = "SGM hook skipped: install the sgm binary to enable governance hooks."
PRETOOL_COMMAND = "pretool"
POSTTOOL_COMMAND = "posttool"
STOP_COMMAND = "stop"


@dataclass(slots=True)
class InitService:
    filesystem: FileSystemAdapter

    def init(self, hooks: str = "none") -> InitResult:
        created_directories: list[str] = []
        created_files: list[str] = []
        updated_files: list[str] = []
        installed_hooks: list[str] = []

        for directory in ("specs", "decisions", ".sgm/work", ".sgm/persisted"):
            if self.filesystem.ensure_directory(directory):
                created_directories.append(directory)

        gitignore_changed = self._ensure_block(
            path=".gitignore",
            block="__pycache__/\n*.pyc\n.sgm/work/\nsgm-state/\n",
            create_if_missing=True,
            heading=None,
        )
        if gitignore_changed == "created":
            created_files.append(".gitignore")
        elif gitignore_changed == "updated":
            updated_files.append(".gitignore")

        agents_changed = self._ensure_agents_guidance()
        if agents_changed == "created":
            created_files.append("AGENTS.md")
        elif agents_changed == "updated":
            updated_files.append("AGENTS.md")

        if self.filesystem.file_exists("CLAUDE.md"):
            claude_changed = self._ensure_claude_guidance()
            if claude_changed == "updated":
                updated_files.append("CLAUDE.md")

        for target, path, installer in self._hook_installers(hooks):
            changed = installer()
            if changed == "created":
                created_files.append(path)
                installed_hooks.append(target)
            elif changed == "updated":
                updated_files.append(path)
                installed_hooks.append(target)
            elif changed == "unchanged" and self.filesystem.file_exists(path):
                installed_hooks.append(target)

        offers = self._build_init_offers(claude_present=self.filesystem.file_exists("CLAUDE.md"))
        return InitResult(
            created_directories=tuple(created_directories),
            created_files=tuple(created_files),
            updated_files=tuple(updated_files),
            offers=offers,
            installed_hooks=tuple(installed_hooks),
        )

    def _ensure_agents_guidance(self) -> str:
        block = self._agents_guidance_block()
        pattern = re.compile(
            r"(?ms)^Use `sgm` when working in governed areas\.\n\n"
            r"(?:- Main agent: orchestrate spec work and hand implementation to a sub-agent\.\n)?"
            r"(?:- Use the narrower behavior spec that matches the work: command model, "
            r"context and delta, validation and focus, persistence, init, or spec format\.\n)?"
            r"(?:- Prefer modules that align with a single spec concern so "
            r"per-spec work and commits stay coherent\.\n)?"
            r"(?:- Do not edit spec files directly during implementation; use "
            r"`sgm propose` for incidental splash expansion\.\n)?"
            r"(?:- Proposal records are durable immediately in `\.sgm/persisted/proposals/`\.\n)?"
            r"(?:- If a touched file is unowned: `(?:uv run )?sgm propose "
            r'<spec-id> <path> "<reason>"`\.\n)?'
            r"(?:- If another spec owns the file: ask a human, then record "
            r"`(?:uv run )?sgm shared allow <owner-spec-id> <spec-id> <path> "
            r'"<reason>"`\.\n)?'
            r"(?:- On delegated shared files, the owner spec wins\.\n)?"
            r"(?:- Coordination files are only for mechanical follow-through "
            r"alongside substantive editable work\.\n)?"
            r"- Before edits: `(?:uv run )?sgm context <spec-file-or-id>`\n"
            r"- After edits: `(?:uv run )?sgm validate(?: <spec-file-or-id>)?`\n"
            r"- Dry run only: `(?:uv run )?sgm validate(?: <spec-file-or-id>)? --no-record`\n"
            r"(?:- If a touched file is ungoverned: `(?:uv run )?sgm propose "
            r'<spec-id> <path> "<reason>"`\n?)?'
        )
        return self._ensure_patterned_block(
            path="AGENTS.md",
            block=block,
            create_if_missing=True,
            pattern=pattern,
        )

    def _ensure_claude_guidance(self) -> str:
        section = self._claude_guidance_section()
        pattern = re.compile(r"(?ms)^## SGM\n.*?(?=^## |\Z)")
        return self._ensure_patterned_block(
            path="CLAUDE.md",
            block=section,
            create_if_missing=False,
            pattern=pattern,
        )

    def _hook_installers(self, hooks: str) -> tuple[tuple[str, str, Any], ...]:
        if hooks == "none":
            return ()
        installers: list[tuple[str, str, Any]] = []
        if hooks in {"claude", "all"}:
            installers.append(("claude", ".claude/settings.json", self._ensure_claude_hooks))
        if hooks in {"codex", "all"}:
            installers.append(("codex", ".codex/hooks.json", self._ensure_codex_hooks))
        return tuple(installers)

    def _ensure_claude_hooks(self) -> str:
        hooks_config = {
            "PreToolUse": [
                self._hook_entry("Bash", self._hook_command(PRETOOL_COMMAND)),
                self._hook_entry("Edit", self._hook_command(PRETOOL_COMMAND)),
                self._hook_entry("Write", self._hook_command(PRETOOL_COMMAND)),
            ],
            "PostToolUse": [self._hook_entry("Bash", self._hook_command(POSTTOOL_COMMAND))],
            "Stop": [self._hook_entry("", self._hook_command(STOP_COMMAND))],
            "SubagentStop": [self._hook_entry("", self._hook_command(STOP_COMMAND))],
        }
        return self._ensure_hook_config(".claude/settings.json", hooks_config)

    def _ensure_codex_hooks(self) -> str:
        hooks_config = {
            "PreToolUse": [self._hook_entry("Bash", self._hook_command(PRETOOL_COMMAND))],
            "PostToolUse": [self._hook_entry("Bash", self._hook_command(POSTTOOL_COMMAND))],
            "Stop": [self._hook_entry("", self._hook_command(STOP_COMMAND))],
        }
        return self._ensure_hook_config(".codex/hooks.json", hooks_config)

    def _hook_command(self, hook_name: str) -> str:
        return (
            "sh -c 'if command -v sgm >/dev/null 2>&1; then "
            f"exec sgm hook {hook_name}; "
            f'fi; printf "%s\\n" "{HOOK_MISSING_MESSAGE}" >&2; exit 0\''
        )

    def _hook_entry(self, matcher: str, command: str) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "hooks": [
                {
                    "type": "command",
                    "command": command,
                }
            ]
        }
        if matcher:
            entry["matcher"] = matcher
        return entry

    def _ensure_hook_config(
        self,
        path: str,
        desired_hooks: dict[str, list[dict[str, Any]]],
    ) -> str:
        current_content = self.filesystem.read_optional_text(path)
        current_config = self._parse_json_object(current_content)
        status = "created" if current_content is None else "unchanged"
        hooks_config = current_config.setdefault("hooks", {})
        if not isinstance(hooks_config, dict):
            hooks_config = {}
            current_config["hooks"] = hooks_config
            status = "updated"

        for event_name, desired_entries in desired_hooks.items():
            existing_entries = hooks_config.get(event_name)
            if not isinstance(existing_entries, list):
                existing_entries = []
                hooks_config[event_name] = existing_entries
                status = "updated"
            for desired_entry in desired_entries:
                if not self._has_hook_entry(existing_entries, desired_entry):
                    existing_entries.append(desired_entry)
                    status = "updated" if current_content is not None else "created"

        rendered = json.dumps(current_config, indent=2, sort_keys=True) + "\n"
        if current_content != rendered:
            self.filesystem.write_text(path, rendered)
            return status
        return "unchanged"

    def _parse_json_object(self, content: str | None) -> dict[str, Any]:
        if content is None:
            return {}
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
        return {}

    def _has_hook_entry(
        self,
        existing_entries: list[Any],
        desired_entry: dict[str, Any],
    ) -> bool:
        desired_matcher = desired_entry.get("matcher", "")
        desired_commands = self._hook_commands(desired_entry)
        for entry in existing_entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("matcher", "") != desired_matcher:
                continue
            if desired_commands.issubset(self._hook_commands(entry)):
                return True
        return False

    def _hook_commands(self, entry: dict[str, Any]) -> set[str]:
        raw_hooks = entry.get("hooks")
        if not isinstance(raw_hooks, list):
            return set()
        commands: set[str] = set()
        for raw_hook in raw_hooks:
            if not isinstance(raw_hook, dict):
                continue
            command = raw_hook.get("command")
            if isinstance(command, str):
                commands.add(command)
        return commands

    def _agents_guidance_block(self) -> str:
        return "\n".join(
            [
                "Use `sgm` when working in governed areas.",
                "",
                "- Main agent: orchestrate spec work and hand implementation to a sub-agent.",
                f"- {SPEC_SELECTION_GUIDANCE_LINE}",
                f"- {AGENTS_GUIDANCE_LINE}",
                f"- {SPEC_EDIT_GUIDANCE_LINE}",
                f"- {PROPOSAL_GUIDANCE_LINE}",
                f"- {UNOWNED_GUIDANCE_LINE}",
                f"- {FOREIGN_OWNER_GUIDANCE_LINE}",
                f"- {OWNER_WINS_GUIDANCE_LINE}",
                f"- {COORDINATION_GUIDANCE_LINE}",
                "- Before edits: `sgm context <spec-file-or-id>`",
                "- After edits: `sgm validate`",
                "- Dry run only: `sgm validate --no-record`",
            ]
        )

    def _claude_guidance_section(self) -> str:
        return "\n".join(
            [
                "## SGM",
                "",
                "Use `sgm` before and after governed edits:",
                "",
                "- Use the narrower behavior spec that matches the work",
                "- `sgm context <spec-file-or-id>` before edits",
                '- If a file is unowned, use `sgm propose <spec-id> <path> "<reason>"`',
                (
                    "- If another spec owns the file, ask a human and record "
                    '`sgm shared allow <owner-spec-id> <spec-id> <path> "<reason>"`'
                ),
                "- On delegated shared files, the owner spec wins",
                (
                    "- Coordination files are only for follow-through alongside "
                    "substantive editable work"
                ),
                "- `sgm validate` after edits",
                "- Prefer modules that align with a single spec concern when practical",
                (
                    "- Do not edit spec files directly during implementation; "
                    "use `sgm propose` for incidental splash expansion"
                ),
                "- Proposal records are durable immediately in `.sgm/persisted/proposals/`",
            ]
        )

    def _ensure_block(
        self,
        path: str,
        block: str,
        create_if_missing: bool,
        heading: str | None,
    ) -> str:
        current_content = self.filesystem.read_optional_text(path)
        if current_content is None:
            if not create_if_missing:
                return "unchanged"
            self.filesystem.write_text(path, f"{block.rstrip()}\n")
            return "created"
        if heading is not None and heading in current_content:
            return "unchanged"
        if block in current_content:
            return "unchanged"
        new_content = current_content.rstrip()
        if new_content:
            new_content += "\n\n"
        new_content += f"{block.rstrip()}\n"
        self.filesystem.write_text(path, new_content)
        return "updated"

    def _ensure_patterned_block(
        self,
        path: str,
        block: str,
        create_if_missing: bool,
        pattern: re.Pattern[str],
    ) -> str:
        current_content = self.filesystem.read_optional_text(path)
        if current_content is None:
            if not create_if_missing:
                return "unchanged"
            self.filesystem.write_text(path, f"{block.rstrip()}\n")
            return "created"

        matches = list(pattern.finditer(current_content))
        if not matches:
            new_content = current_content.rstrip()
            if new_content:
                new_content += "\n\n"
            new_content += f"{block.rstrip()}\n"
            self.filesystem.write_text(path, new_content)
            return "updated"

        first_match = matches[0]
        prefix = current_content[: first_match.start()].rstrip()
        suffix = current_content[first_match.end() :]
        suffix = pattern.sub("", suffix).strip()
        parts = [prefix, block.rstrip(), suffix]
        new_content = "\n\n".join(part for part in parts if part) + "\n"
        if new_content == current_content:
            return "unchanged"
        self.filesystem.write_text(path, new_content)
        return "updated"

    def _build_init_offers(self, claude_present: bool) -> tuple[InitOffer, ...]:
        offers: list[InitOffer] = []
        if claude_present:
            offers.append(
                InitOffer(
                    target="claude",
                    message=(
                        "CLAUDE.md detected; keep Claude-specific SGM workflow guidance there."
                    ),
                )
            )
        else:
            offers.append(
                InitOffer(
                    target="codex/gemini",
                    message=(
                        "No CLAUDE.md detected; use AGENTS.md as the default "
                        "place for Codex/Gemini SGM workflow guidance."
                    ),
                )
            )
        return tuple(offers)
