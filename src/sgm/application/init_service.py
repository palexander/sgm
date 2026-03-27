from __future__ import annotations

import re
from dataclasses import dataclass

from sgm.adapters.filesystem import FileSystemAdapter
from sgm.domain.models import InitOffer, InitResult

AGENTS_GUIDANCE_LINE = (
    "Prefer modules that align with a single spec concern so "
    "per-spec work and commits stay coherent."
)
PROPOSAL_GUIDANCE_LINE = (
    "Proposal records are durable immediately in `.sgm/persisted/proposals/`."
)


@dataclass(slots=True)
class InitService:
    filesystem: FileSystemAdapter

    def init(self) -> InitResult:
        created_directories: list[str] = []
        created_files: list[str] = []
        updated_files: list[str] = []

        for directory in ("specs", "decisions", ".sgm/work", ".sgm/persisted"):
            if self.filesystem.ensure_directory(directory):
                created_directories.append(directory)

        gitignore_changed = self._ensure_block(
            path=".gitignore",
            block="__pycache__/\n*.pyc\n.sgm/work/\n.sgm/persisted/validations/\nsgm-state/\n",
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

        offers = self._build_init_offers(
            claude_present=self.filesystem.file_exists("CLAUDE.md")
        )
        return InitResult(
            created_directories=tuple(created_directories),
            created_files=tuple(created_files),
            updated_files=tuple(updated_files),
            offers=offers,
        )

    def _ensure_agents_guidance(self) -> str:
        block = self._agents_guidance_block()
        pattern = re.compile(
            r"(?ms)^Use `sgm` when working in governed areas\.\n\n"
            r"(?:- Main agent: orchestrate spec work and hand implementation to a sub-agent\.\n)?"
            r"(?:- Prefer modules that align with a single spec concern so "
            r"per-spec work and commits stay coherent\.\n)?"
            r"(?:- Proposal records are durable immediately in `\.sgm/persisted/proposals/`\.\n)?"
            r"(?:- Before commit or handoff: `(?:uv run )?sgm persist`\n)?"
            r"- Before edits: `(?:uv run )?sgm context <spec-file-or-id>`\n"
            r"- After edits: `(?:uv run )?sgm validate(?: <spec-file-or-id>)?`\n"
            r"- Dry run only: `(?:uv run )?sgm validate(?: <spec-file-or-id>)? --no-record`\n"
            r"- If a touched file is ungoverned: `(?:uv run )?sgm propose "
            r"<spec-id> <path> \"<reason>\"`\n?"
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

    def _agents_guidance_block(self) -> str:
        return "\n".join(
            [
                "Use `sgm` when working in governed areas.",
                "",
                "- Main agent: orchestrate spec work and hand implementation to a sub-agent.",
                f"- {AGENTS_GUIDANCE_LINE}",
                f"- {PROPOSAL_GUIDANCE_LINE}",
                "- Before edits: `sgm context <spec-file-or-id>`",
                "- After edits: `sgm validate`",
                "- Dry run only: `sgm validate --no-record`",
                '- If a touched file is ungoverned: `sgm propose <spec-id> <path> "<reason>"`',
            ]
        )

    def _claude_guidance_section(self) -> str:
        return "\n".join(
            [
                "## SGM",
                "",
                "Use `sgm` before and after governed edits:",
                "",
                "- `sgm context <spec-file-or-id>` before edits",
                "- `sgm validate` after edits",
                "- Prefer modules that align with a single spec concern when practical",
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
                        "CLAUDE.md detected; keep Claude-specific SGM workflow "
                        "guidance there."
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
