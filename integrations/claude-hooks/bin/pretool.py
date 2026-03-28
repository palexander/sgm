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
    is_governed_file,
    is_sgm_context_command,
    is_sgm_validate_command,
    load_state,
    project_root,
    save_state,
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
    cwd = project_root(payload)
    state = load_state(cwd)
    tool_name = get_tool_name(payload)

    if tool_name == "Bash":
        command = command_text(payload)
        if is_force_command(command):
            state.force_override = True
            save_state(cwd, state)
            allow()
            return 0
        if is_sgm_context_command(command) or is_sgm_validate_command(command):
            allow()
            return 0
        if is_editing_shell_command(command):
            if not state.active_spec_id or not state.governed_files:
                deny(
                    "Run `sgm context <spec>` before editing so Claude has a focused spec boundary."
                )
                return 0
            for governed in state.governed_files:
                if governed in command:
                    save_state(cwd, state)
                    allow()
                return 0
            if not state.force_override:
                deny(
                    "Current work is focused on "
                    f"{state.active_spec_id}. Run `sgm context <spec>` or use "
                    "`--force` before editing outside the governed file set."
                )
                return 0
        allow()
        return 0

    if tool_name in {"Edit", "Write"}:
        paths = file_paths_from_payload(payload, cwd)
        if not paths:
            allow()
            return 0
        if state.force_override:
            state.dirty_since_validate = True
            save_state(cwd, state)
            allow()
            return 0
        if not state.active_spec_id or not state.governed_files:
            deny(
                "Run `sgm context <spec>` before editing so Claude knows which files are in scope."
            )
            return 0
        for raw_path in paths:
            if not is_governed_file(raw_path, state.governed_files):
                deny(
                    f"{Path(raw_path).name} is outside the active spec scope. "
                    "Propose it first, or use `--force` if this is intentional."
                )
                return 0
        state.dirty_since_validate = True
        save_state(cwd, state)
        allow()
        return 0

    allow()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
