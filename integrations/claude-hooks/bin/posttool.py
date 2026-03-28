#!/usr/bin/env python3
from __future__ import annotations

import json
import sys

from _common import (
    command_text,
    extract_text,
    get_tool_name,
    get_tool_response,
    is_sgm_context_command,
    is_sgm_validate_command,
    load_state,
    parse_context_output,
    parse_validation_output,
    project_root,
    save_state,
)


def main() -> int:
    payload = json.load(sys.stdin)
    cwd = project_root(payload)
    state = load_state(cwd)
    tool_name = get_tool_name(payload)

    if tool_name != "Bash":
        return 0

    command = command_text(payload)
    tool_response = get_tool_response(payload)
    response_text = extract_text(tool_response)

    if is_sgm_context_command(command):
        active_spec_id, governed_files = parse_context_output(response_text)
        if active_spec_id:
            state.active_spec_id = active_spec_id
        state.governed_files = governed_files
        state.last_context_command = command
        save_state(cwd, state)
        return 0

    if is_sgm_validate_command(command):
        result = parse_validation_output(response_text)
        state.last_validate_command = command
        state.last_validation_result = result
        if result == "pass":
            state.dirty_since_validate = False
            state.force_override = False
        save_state(cwd, state)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
