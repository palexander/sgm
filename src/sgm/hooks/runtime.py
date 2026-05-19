from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STATE_RELATIVE_PATH = Path(".sgm/work/claude-hook-state.json")
COMMAND_TOOL_NAMES = {"Bash", "Shell", "shell", "exec_command"}
EDIT_TOOL_NAMES = {"Edit", "Write", "MultiEdit", "apply_patch"}


@dataclass
class HookState:
    active_spec_id: str | None = None
    active_spec_path: str | None = None
    editable_files: list[str] = field(default_factory=list)
    coordination_files: list[str] = field(default_factory=list)
    dirty_since_validate: bool = False
    semantic_review_required: bool = False
    force_override: bool = False
    last_context_command: str | None = None
    last_validate_command: str | None = None
    last_validation_result: str | None = None
    last_semantic_review_command: str | None = None


def read_input() -> dict[str, Any]:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def working_directory(payload: dict[str, Any]) -> Path:
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        return Path(cwd).resolve()
    return Path.cwd().resolve()


def project_root(payload: dict[str, Any]) -> Path:
    current = working_directory(payload)
    while True:
        git_marker = current / ".git"
        if git_marker.is_dir() or git_marker.is_file():
            return current
        if current.parent == current:
            return working_directory(payload)
        current = current.parent


def state_path(repo_root: Path) -> Path:
    return repo_root / STATE_RELATIVE_PATH


def load_state(repo_root: Path) -> HookState:
    path = state_path(repo_root)
    if not path.exists():
        return HookState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return HookState()
    if not isinstance(raw, dict):
        return HookState()
    state = HookState(
        active_spec_id=raw.get("active_spec_id"),
        active_spec_path=raw.get("active_spec_path"),
        editable_files=list(raw.get("editable_files") or []),
        coordination_files=list(raw.get("coordination_files") or []),
        dirty_since_validate=bool(raw.get("dirty_since_validate", False)),
        semantic_review_required=bool(raw.get("semantic_review_required", False)),
        force_override=bool(raw.get("force_override", False)),
        last_context_command=raw.get("last_context_command"),
        last_validate_command=raw.get("last_validate_command"),
        last_validation_result=raw.get("last_validation_result"),
        last_semantic_review_command=raw.get("last_semantic_review_command"),
    )
    return normalize_state_paths(state, repo_root)


def save_state(repo_root: Path, state: HookState) -> None:
    path = state_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized_state = normalize_state_paths(state, repo_root)
    path.write_text(
        json.dumps(normalized_state.__dict__, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def normalized_path(raw_path: str, cwd: Path, repo_root: Path | None = None) -> str:
    path = Path(raw_path)
    current_root = cwd.resolve()
    target_root = repo_root.resolve() if repo_root is not None else current_root
    if not path.is_absolute():
        path = current_root / path
    resolved_path = path.resolve()
    try:
        return Path(os.path.relpath(resolved_path, target_root)).as_posix()
    except ValueError:
        return resolved_path.as_posix()


def normalize_state_paths(state: HookState, repo_root: Path) -> HookState:
    if state.active_spec_path:
        state.active_spec_path = _normalize_stored_path(state.active_spec_path, repo_root)
    state.editable_files = [
        _normalize_stored_path(path, repo_root)
        for path in state.editable_files
        if isinstance(path, str) and path
    ]
    state.coordination_files = [
        _normalize_stored_path(path, repo_root)
        for path in state.coordination_files
        if isinstance(path, str) and path
    ]
    return state


def _normalize_stored_path(raw_path: str, repo_root: Path) -> str:
    path = Path(raw_path)
    if not path.is_absolute():
        return path.as_posix()
    return normalized_path(raw_path, repo_root, repo_root)


def event_name(payload: dict[str, Any], default: str) -> str:
    value = payload.get("hook_event_name")
    if isinstance(value, str) and value:
        return value
    value = payload.get("hookEventName")
    if isinstance(value, str) and value:
        return value
    return default


def get_tool_name(payload: dict[str, Any]) -> str:
    for key in ("tool_name", "toolName", "tool", "name"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def get_tool_input(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("tool_input")
    if isinstance(value, dict):
        return value
    value = payload.get("toolInput")
    return value if isinstance(value, dict) else {}


def get_tool_response(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("tool_response", "toolResponse", "response", "result"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


def user_prompt_text(payload: dict[str, Any]) -> str:
    for key in ("prompt", "user_prompt", "userPrompt", "message", "text"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def extract_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        parts: list[str] = []
        for key in ("stdout", "stderr", "output", "content", "text", "message"):
            nested = value.get(key)
            if nested is not None:
                extracted = extract_text(nested)
                if extracted:
                    parts.append(extracted)
        if parts:
            return "\n".join(parts)
        return "\n".join(extract_text(item) for item in value.values())
    if isinstance(value, list):
        return "\n".join(extract_text(item) for item in value)
    return ""


def command_text(payload: dict[str, Any]) -> str:
    tool_input = get_tool_input(payload)
    for source in (tool_input, payload):
        for key in ("command", "cmd"):
            value = source.get(key)
            if isinstance(value, str):
                return value
    return ""


def file_paths_from_payload(
    payload: dict[str, Any],
    cwd: Path,
    repo_root: Path | None = None,
) -> list[str]:
    paths: list[str] = []
    for source in (get_tool_input(payload), payload):
        for key in ("file_path", "filePath", "path", "source"):
            value = source.get(key)
            if isinstance(value, str) and value:
                paths.append(normalized_path(value, cwd, repo_root))
        value = source.get("file_paths") or source.get("filePaths")
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item:
                    paths.append(normalized_path(item, cwd, repo_root))
    return list(dict.fromkeys(paths))


def is_command_tool(tool_name: str, command: str) -> bool:
    return tool_name in COMMAND_TOOL_NAMES or bool(command)


def is_edit_tool(tool_name: str) -> bool:
    return tool_name in EDIT_TOOL_NAMES


def is_force_command(command: str) -> bool:
    return "--force" in command or "--allow" in command


def is_sgm_context_command(command: str) -> bool:
    return command.startswith("sgm context ")


def is_sgm_validate_command(command: str) -> bool:
    return command.startswith("sgm validate")


def is_sgm_semantic_review_command(command: str) -> bool:
    return command.startswith("sgm hook semantic-reviewed")


def is_editing_shell_command(command: str) -> bool:
    lowered = command.lower()
    write_markers = (
        " > ",
        ">>",
        "| tee ",
        " tee ",
        "sed -i",
        "perl -0pi",
        "python - <<",
        "python3 - <<",
        "cat >",
        "printf ",
        "cp ",
        "mv ",
        "rm ",
        "patch ",
        "git apply",
    )
    return any(marker in lowered for marker in write_markers)


def parse_context_output(output: str) -> tuple[str | None, list[str], list[str]]:
    active_spec_id: str | None = None
    editable_files: list[str] = []
    coordination_files: list[str] = []
    in_editable = False
    in_coordination = False
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("[EDITABLE]"):
            in_editable = True
            in_coordination = False
            continue
        if stripped.startswith("[COORDINATION]"):
            in_editable = False
            in_coordination = True
            continue
        if stripped.startswith("["):
            in_editable = False
            in_coordination = False
        if active_spec_id is None:
            match = re.match(r"(spec-[a-z0-9-]+)", stripped)
            if match:
                active_spec_id = match.group(1)
        if in_editable and not stripped.startswith("[") and stripped not in editable_files:
            editable_files.append(stripped)
        if in_coordination and not stripped.startswith("["):
            path = stripped.split(" <- ", maxsplit=1)[0]
            if path != stripped and path not in coordination_files:
                coordination_files.append(path)
    return active_spec_id, editable_files, coordination_files


def parse_validation_output(output: str) -> str | None:
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("[PASS]"):
            return "pass"
        if stripped.startswith("[WARN]"):
            return "warn"
        if stripped.startswith("[FAIL]"):
            return "fail"
    return None


def is_allowed_file(path: str, editable_files: list[str], coordination_files: list[str]) -> bool:
    return path in editable_files or path in coordination_files


def deny(payload: dict[str, Any], message: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": event_name(payload, "PreToolUse"),
                "permissionDecision": "deny",
                "permissionDecisionReason": message,
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


def pretool_allow(payload: dict[str, Any]) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": event_name(payload, "PreToolUse"),
                "permissionDecision": "allow",
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


def block_stop(reason: str) -> int:
    json.dump({"decision": "block", "reason": reason}, sys.stdout)
    sys.stdout.write("\n")
    return 0


def add_user_prompt_context(payload: dict[str, Any], message: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": event_name(payload, "UserPromptSubmit"),
                "additionalContext": message,
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


def user_prompt_guidance(prompt: str) -> str:
    lines = [
        "SGM pre-work check:",
        "Before implementing, make sure the user's request is represented in an SGM spec.",
        "If an existing spec covers the behavior, run `sgm context <spec-file-or-id>` before edits.",
        "If no existing spec covers it, create or update the governing spec before code changes.",
        (
            "For ownership gaps discovered during implementation, use `sgm propose` for "
            "unowned files or ask a human before `sgm shared allow` for another spec's files."
        ),
    ]
    if prompt:
        lines.extend(["", f"User request: {prompt}"])
    return "\n".join(lines)


def semantic_review_prompt(state: HookState) -> str:
    spec = state.active_spec_path or state.active_spec_id or "<active-spec>"
    return "\n".join(
        [
            "Before finishing, run a quick SGM semantic alignment eval.",
            "",
            f"Active spec: {spec}",
            "",
            "Compare the active spec against the current diff and answer:",
            "1. Does every substantive code change implement or support the active spec?",
            "2. Did the implementation add behavior not stated in the spec?",
            "3. Did it touch files that imply the spec should expand?",
            "4. Are there docs or tests that now claim behavior the spec does not cover?",
            "",
            "If aligned, record the review with:",
            "  sgm hook semantic-reviewed",
            "",
            "Then run:",
            f"  sgm validate {spec}",
            "",
            "If drift exists, update the spec or governance record first, then record "
            "the review and validate.",
        ]
    )


def run_user_prompt() -> int:
    payload = read_input()
    add_user_prompt_context(payload, user_prompt_guidance(user_prompt_text(payload)))
    return 0


def run_pretool() -> int:
    payload = read_input()
    command_cwd = working_directory(payload)
    repo_root = project_root(payload)
    state = load_state(repo_root)
    tool_name = get_tool_name(payload)
    command = command_text(payload)

    if is_command_tool(tool_name, command):
        if is_force_command(command):
            state.force_override = True
            save_state(repo_root, state)
            pretool_allow(payload)
            return 0
        if is_sgm_context_command(command) or is_sgm_validate_command(command):
            pretool_allow(payload)
            return 0
        if is_sgm_semantic_review_command(command):
            pretool_allow(payload)
            return 0
        if is_editing_shell_command(command):
            if not state.active_spec_id or not (state.editable_files or state.coordination_files):
                deny(
                    payload,
                    "Run `sgm context <spec>` before editing so Claude has a "
                    "focused spec boundary.",
                )
                return 0
            for allowed in [*state.editable_files, *state.coordination_files]:
                if allowed in command:
                    state.dirty_since_validate = True
                    state.semantic_review_required = True
                    save_state(repo_root, state)
                    pretool_allow(payload)
                    return 0
            if not state.force_override:
                deny(
                    payload,
                    "Current work is focused on "
                    f"{state.active_spec_id}. Run `sgm context <spec>` or use "
                    "`--force` before editing outside the editable or coordination file set.",
                )
                return 0
        pretool_allow(payload)
        return 0

    if is_edit_tool(tool_name):
        paths = file_paths_from_payload(payload, command_cwd, repo_root)
        if not paths:
            pretool_allow(payload)
            return 0
        if state.force_override:
            state.dirty_since_validate = True
            state.semantic_review_required = True
            save_state(repo_root, state)
            pretool_allow(payload)
            return 0
        if not state.active_spec_id or not (state.editable_files or state.coordination_files):
            deny(
                payload,
                "Run `sgm context <spec>` before editing so Claude knows which "
                "files are editable or coordination spillover.",
            )
            return 0
        for raw_path in paths:
            if not is_allowed_file(raw_path, state.editable_files, state.coordination_files):
                deny(
                    payload,
                    f"{Path(raw_path).name} is outside the active spec scope. "
                    "If it is unowned, use `sgm propose`; if another spec owns it, "
                    "ask a human and record `sgm shared allow`; otherwise use `--force`.",
                )
                return 0
        state.dirty_since_validate = True
        state.semantic_review_required = True
        save_state(repo_root, state)
        pretool_allow(payload)
        return 0

    pretool_allow(payload)
    return 0


def run_posttool() -> int:
    payload = read_input()
    repo_root = project_root(payload)
    state = load_state(repo_root)
    tool_name = get_tool_name(payload)
    command = command_text(payload)

    if not is_command_tool(tool_name, command):
        return 0

    tool_response = get_tool_response(payload)
    response_text = extract_text(tool_response)

    if is_sgm_context_command(command):
        active_spec_id, editable_files, coordination_files = parse_context_output(response_text)
        if active_spec_id:
            state.active_spec_id = active_spec_id
        state.editable_files = editable_files
        state.coordination_files = coordination_files
        state.last_context_command = command
        save_state(repo_root, state)
        return 0

    if is_sgm_validate_command(command):
        result = parse_validation_output(response_text)
        state.last_validate_command = command
        state.last_validation_result = result
        if result == "pass" and not state.semantic_review_required:
            state.dirty_since_validate = False
            state.force_override = False
        save_state(repo_root, state)
        return 0

    if is_sgm_semantic_review_command(command):
        state.semantic_review_required = False
        state.last_semantic_review_command = command
        save_state(repo_root, state)
        return 0

    return 0


def run_semantic_reviewed() -> int:
    repo_root = project_root({})
    state = load_state(repo_root)
    state.semantic_review_required = False
    state.last_semantic_review_command = "sgm hook semantic-reviewed"
    save_state(repo_root, state)
    sys.stdout.write("[SEMANTIC-REVIEWED] recorded semantic alignment review\n")
    return 0


def run_stop() -> int:
    payload = read_input()
    repo_root = project_root(payload)
    state = load_state(repo_root)

    if state.force_override:
        return 0

    if state.semantic_review_required:
        return block_stop(semantic_review_prompt(state))

    if state.dirty_since_validate:
        return block_stop(
            "SGM still has unvalidated edits in the current spec scope. "
            "Run `sgm validate` before finishing, or use `--force` if you "
            "intentionally want to stop early."
        )

    return 0
