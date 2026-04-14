#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STATE_RELATIVE_PATH = Path(".sgm/work/claude-hook-state.json")


@dataclass
class HookState:
    active_spec_id: str | None = None
    active_spec_path: str | None = None
    editable_files: list[str] = field(default_factory=list)
    coordination_files: list[str] = field(default_factory=list)
    dirty_since_validate: bool = False
    force_override: bool = False
    last_context_command: str | None = None
    last_validate_command: str | None = None
    last_validation_result: str | None = None


def read_input() -> dict[str, Any]:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def working_directory(payload: dict[str, Any]) -> Path:
    cwd = payload.get("cwd")
    return Path(cwd).resolve() if isinstance(cwd, str) and cwd else Path.cwd().resolve()


def project_root(payload: dict[str, Any]) -> Path:
    start = working_directory(payload)
    current = start
    while True:
        git_marker = current / ".git"
        if git_marker.is_dir() or git_marker.is_file():
            return current
        if current.parent == current:
            return start
        current = current.parent


def state_path(cwd: Path) -> Path:
    return cwd / STATE_RELATIVE_PATH


def load_state(cwd: Path) -> HookState:
    path = state_path(cwd)
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
        force_override=bool(raw.get("force_override", False)),
        last_context_command=raw.get("last_context_command"),
        last_validate_command=raw.get("last_validate_command"),
        last_validation_result=raw.get("last_validation_result"),
    )
    state = normalize_state_paths(state, cwd)
    return state


def save_state(cwd: Path, state: HookState) -> None:
    path = state_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized_state = normalize_state_paths(state, cwd)
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


def normalize_state_paths(state: HookState, cwd: Path) -> HookState:
    if state.active_spec_path:
        state.active_spec_path = _normalize_stored_path(state.active_spec_path, cwd)
    state.editable_files = [
        _normalize_stored_path(path, cwd)
        for path in state.editable_files
        if isinstance(path, str) and path
    ]
    state.coordination_files = [
        _normalize_stored_path(path, cwd)
        for path in state.coordination_files
        if isinstance(path, str) and path
    ]
    return state


def _normalize_stored_path(raw_path: str, repo_root: Path) -> str:
    path = Path(raw_path)
    if not path.is_absolute():
        return path.as_posix()
    return normalized_path(raw_path, repo_root, repo_root)


def get_tool_name(payload: dict[str, Any]) -> str:
    value = payload.get("tool_name")
    return value if isinstance(value, str) else ""


def get_tool_input(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("tool_input")
    return value if isinstance(value, dict) else {}


def get_tool_response(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("tool_response")
    return value if isinstance(value, dict) else {}


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
        extra_parts: list[str] = []
        for item in value.values():
            extracted = extract_text(item)
            if extracted:
                extra_parts.append(extracted)
        return "\n".join(extra_parts)
    if isinstance(value, list):
        return "\n".join(extract_text(item) for item in value)
    return ""


def command_text(payload: dict[str, Any]) -> str:
    tool_input = get_tool_input(payload)
    command = tool_input.get("command")
    return command if isinstance(command, str) else ""


def file_paths_from_payload(
    payload: dict[str, Any],
    cwd: Path,
    repo_root: Path | None = None,
) -> list[str]:
    tool_input = get_tool_input(payload)
    paths: list[str] = []
    for key in ("file_path", "path", "source"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            paths.append(normalized_path(value, cwd, repo_root))
    value = tool_input.get("file_paths")
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item:
                paths.append(normalized_path(item, cwd, repo_root))
    return paths


def is_force_command(command: str) -> bool:
    return "--force" in command or "--allow" in command


def is_sgm_context_command(command: str) -> bool:
    return command.startswith("sgm context ")


def is_sgm_validate_command(command: str) -> bool:
    return command.startswith("sgm validate")


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
