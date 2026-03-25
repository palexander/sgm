from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import yaml

from sgm.domain.errors import SpecValidationError
from sgm.domain.models import (
    AssertionDocument,
    AssertionKind,
    AssertionSeverity,
    GovernanceSelector,
    SpecDocument,
    SpecStatus,
)


def load_spec_document(path: Path, repo_root: Path) -> SpecDocument:
    source_text: str = path.read_text(encoding="utf-8")
    raw_document: object = yaml.safe_load(source_text)
    if not isinstance(raw_document, dict):
        raise SpecValidationError("spec file must contain a mapping")

    spec_mapping: dict[str, Any] = cast(dict[str, Any], raw_document)
    assertions_raw: object = spec_mapping.get("assertions", [])
    governs_raw: object = spec_mapping.get("governs", [])

    if not isinstance(assertions_raw, list):
        raise SpecValidationError("assertions must be a list")
    if not isinstance(governs_raw, list):
        raise SpecValidationError("governs must be a list")

    assertions: list[AssertionDocument] = []
    for assertion_item in assertions_raw:
        if not isinstance(assertion_item, dict):
            raise SpecValidationError("each assertion must be a mapping")
        config: object = assertion_item.get("config")
        if not isinstance(config, dict):
            raise SpecValidationError("assertion config must be a mapping")
        for value in config.values():
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise SpecValidationError("assertion config values must be string lists")
        assertions.append(
            AssertionDocument(
                id=_require_str(assertion_item, "id"),
                rule=_require_str(assertion_item, "rule"),
                hint=_optional_str(assertion_item, "hint"),
                kind=cast(
                    AssertionKind,
                    _require_literal(assertion_item, "kind", {"structural"}),
                ),
                severity=cast(
                    AssertionSeverity,
                    _require_literal(assertion_item, "severity", {"error", "warning"}),
                ),
                check=_require_str(assertion_item, "check"),
                config=cast(dict[str, list[str]], config),
            )
        )

    governs: list[GovernanceSelector] = []
    for governs_item in governs_raw:
        if not isinstance(governs_item, dict):
            raise SpecValidationError("each governs entry must be a mapping")
        governs.append(
            GovernanceSelector(
                selector=_require_str(governs_item, "selector"),
                priority=_require_int(governs_item, "priority"),
            )
        )

    return SpecDocument(
        id=_require_str(spec_mapping, "id"),
        source_path=path.resolve().relative_to(repo_root.resolve()).as_posix(),
        source_text=source_text,
        title=_require_str(spec_mapping, "title"),
        version=_require_int(spec_mapping, "version"),
        text=_require_str(spec_mapping, "text"),
        status=cast(
            SpecStatus,
            _require_literal(spec_mapping, "status", {"draft", "active", "deprecated"}),
        ),
        author=_require_str(spec_mapping, "author"),
        warn_below=_require_float(spec_mapping, "warn_below", default=0.8),
        assertions=tuple(assertions),
        governs=tuple(governs),
    )


def serialize_assertion_config(config: dict[str, list[str]]) -> str:
    return json.dumps(config, sort_keys=True)


def _require_str(mapping: dict[str, Any], key: str) -> str:
    value: object = mapping.get(key)
    if not isinstance(value, str) or value == "":
        raise SpecValidationError(f"{key} must be a non-empty string")
    return value


def _optional_str(mapping: dict[str, Any], key: str) -> str | None:
    value: object = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise SpecValidationError(f"{key} must be a string when present")
    return value


def _require_int(mapping: dict[str, Any], key: str) -> int:
    value: object = mapping.get(key)
    if not isinstance(value, int):
        raise SpecValidationError(f"{key} must be an integer")
    return value


def _require_float(mapping: dict[str, Any], key: str, default: float) -> float:
    value: object = mapping.get(key, default)
    if not isinstance(value, int | float):
        raise SpecValidationError(f"{key} must be numeric")
    return float(value)


def _require_literal(mapping: dict[str, Any], key: str, allowed: set[str]) -> str:
    value: str = _require_str(mapping, key)
    if value not in allowed:
        raise SpecValidationError(f"{key} must be one of {sorted(allowed)}")
    return value
