#!/usr/bin/env python3
from __future__ import annotations

import json
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
    governed_files: list[str] = field(default_factory=list)
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


def project_root(payload: dict[str, Any]) -> Path:
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        return Path(cwd).resolve()
    return Path.cwd().resolve()


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
    return HookState(
        active_spec_id=raw.get("active_spec_id"),
        active_spec_path=raw.get("active_spec_path"),
        governed_files=list(raw.get("governed_files") or []),
        dirty_since_validate=bool(raw.get("dirty_since_validate", False)),
        force_override=bool(raw.get("force_override", False)),
        last_context_command=raw.get("last_context_command"),
        last_validate_command=raw.get("last_validate_command"),
        last_validation_result=raw.get("last_validation_result"),
    )


def save_state(cwd: Path, state: HookState) -> None:
    path = state_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.__dict__, indent=2, sort_keys=True), encoding="utf-8")


def normalized_path(raw_path: str, cwd: Path) -> str:
    path = Path(raw_path)
    if not path.is_absolute():
        path = cwd / path
    try:
        return path.resolve().relative_to(cwd).as_posix()
    except ValueError:
        return path.resolve().as_posix()


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


def file_paths_from_payload(payload: dict[str, Any], cwd: Path) -> list[str]:
    tool_input = get_tool_input(payload)
    paths: list[str] = []
    for key in ("file_path", "path", "source"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            paths.append(normalized_path(value, cwd))
    value = tool_input.get("file_paths")
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item:
                paths.append(normalized_path(item, cwd))
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


def parse_context_output(output: str) -> tuple[str | None, list[str]]:
    active_spec_id: str | None = None
    governed_files: list[str] = []
    in_files = False
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("[FILES]"):
            in_files = True
            continue
        if stripped.startswith("[") and not stripped.startswith("[FILES]"):
            in_files = False
        if active_spec_id is None:
            match = re.match(r"(spec-[a-z0-9-]+)", stripped)
            if match:
                active_spec_id = match.group(1)
        if in_files and not stripped.startswith("[") and stripped not in governed_files:
            governed_files.append(stripped)
    return active_spec_id, governed_files


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


def is_governed_file(path: str, governed_files: list[str]) -> bool:
    return path in governed_files
