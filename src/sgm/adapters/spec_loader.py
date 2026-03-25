from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

from sgm.domain.errors import SpecValidationError
from sgm.domain.models import GovernanceSelector, SpecDocument, SpecStatus


def load_spec_document(path: Path, repo_root: Path) -> SpecDocument:
    source_text: str = path.read_text(encoding="utf-8")
    raw_document: object = yaml.safe_load(source_text)
    if not isinstance(raw_document, dict):
        raise SpecValidationError("spec file must contain a mapping")

    spec_mapping: dict[str, Any] = cast(dict[str, Any], raw_document)
    governs_raw: object = spec_mapping.get("governs", [])
    if not isinstance(governs_raw, list):
        raise SpecValidationError("governs must be a list")

    governs: list[GovernanceSelector] = []
    for governs_item in governs_raw:
        if not isinstance(governs_item, dict):
            raise SpecValidationError("each governs entry must be a mapping")
        governs.append(
            GovernanceSelector(
                selector=_require_str(governs_item, "selector"),
                priority=_optional_int(governs_item, "priority", default=1),
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
        governs=tuple(governs),
    )


def _require_str(mapping: dict[str, Any], key: str) -> str:
    value: object = mapping.get(key)
    if not isinstance(value, str) or value == "":
        raise SpecValidationError(f"{key} must be a non-empty string")
    return value


def _require_int(mapping: dict[str, Any], key: str) -> int:
    value: object = mapping.get(key)
    if not isinstance(value, int):
        raise SpecValidationError(f"{key} must be an integer")
    return value


def _optional_int(mapping: dict[str, Any], key: str, default: int) -> int:
    value: object = mapping.get(key, default)
    if not isinstance(value, int):
        raise SpecValidationError(f"{key} must be an integer")
    return value


def _require_literal(mapping: dict[str, Any], key: str, allowed: set[str]) -> str:
    value: str = _require_str(mapping, key)
    if value not in allowed:
        raise SpecValidationError(f"{key} must be one of {sorted(allowed)}")
    return value
