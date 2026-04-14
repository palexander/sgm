#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

from _common import (
    command_text,
    file_paths_from_payload,
    get_tool_name,
    is_editing_shell_command,
    is_force_command,
    is_allowed_file,
    is_sgm_context_command,
    is_sgm_validate_command,
    load_state,
    project_root,
    save_state,
    working_directory,
)


def deny(message: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": message,
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


def allow() -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


def main() -> int:
    payload = json.load(sys.stdin)
    command_cwd = working_directory(payload)
    repo_root = project_root(payload)
    state = load_state(repo_root)
    tool_name = get_tool_name(payload)

    if tool_name == "Bash":
        command = command_text(payload)
        if is_force_command(command):
            state.force_override = True
            save_state(repo_root, state)
            allow()
            return 0
        if is_sgm_context_command(command) or is_sgm_validate_command(command):
            allow()
            return 0
        if is_editing_shell_command(command):
            if not state.active_spec_id or not (state.editable_files or state.coordination_files):
                deny(
                    "Run `sgm context <spec>` before editing so Claude has a focused spec boundary."
                )
                return 0
            for allowed in [*state.editable_files, *state.coordination_files]:
                if allowed in command:
                    save_state(repo_root, state)
                    allow()
                    return 0
            if not state.force_override:
                deny(
                    "Current work is focused on "
                    f"{state.active_spec_id}. Run `sgm context <spec>` or use "
                    "`--force` before editing outside the editable or coordination file set."
                )
                return 0
        allow()
        return 0

    if tool_name in {"Edit", "Write"}:
        paths = file_paths_from_payload(payload, command_cwd, repo_root)
        if not paths:
            allow()
            return 0
        if state.force_override:
            state.dirty_since_validate = True
            save_state(repo_root, state)
            allow()
            return 0
        if not state.active_spec_id or not (state.editable_files or state.coordination_files):
            deny(
                "Run `sgm context <spec>` before editing so Claude knows which files are editable or coordination spillover."
            )
            return 0
        for raw_path in paths:
            if not is_allowed_file(raw_path, state.editable_files, state.coordination_files):
                deny(
                    f"{Path(raw_path).name} is outside the active spec scope. "
                    "If it is unowned, use `sgm propose`; if another spec owns it, ask a human and record `sgm shared allow`; otherwise use `--force`."
                )
                return 0
        state.dirty_since_validate = True
        save_state(repo_root, state)
        allow()
        return 0

    allow()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
