from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

from sgm.domain.errors import SpecValidationError
from sgm.domain.models import DecisionDocument, DecisionSelector, DecisionStatus


def load_decision_document(path: Path, repo_root: Path) -> DecisionDocument:
    source_text: str = path.read_text(encoding="utf-8")
    raw_document: object = yaml.safe_load(source_text)
    if not isinstance(raw_document, dict):
        raise SpecValidationError("decision file must contain a mapping")

    decision_mapping: dict[str, Any] = cast(dict[str, Any], raw_document)
    touches_raw: object = decision_mapping.get("touches", [])
    if not isinstance(touches_raw, list):
        raise SpecValidationError("touches must be a list")

    touches: list[DecisionSelector] = []
    for touch_item in touches_raw:
        if not isinstance(touch_item, dict):
            raise SpecValidationError("each touches entry must be a mapping")
        touches.append(DecisionSelector(selector=_require_str(touch_item, "selector")))

    return DecisionDocument(
        id=_require_str(decision_mapping, "id"),
        source_path=path.resolve().relative_to(repo_root.resolve()).as_posix(),
        source_text=source_text,
        title=_require_str(decision_mapping, "title"),
        status=cast(
            DecisionStatus,
            _require_literal(decision_mapping, "status", {"draft", "active", "superseded"}),
        ),
        context=_require_str(decision_mapping, "context"),
        decision=_require_str(decision_mapping, "decision"),
        consequences=_require_str(decision_mapping, "consequences"),
        touches=tuple(touches),
    )


def _require_str(mapping: dict[str, Any], key: str) -> str:
    value: object = mapping.get(key)
    if not isinstance(value, str) or value == "":
        raise SpecValidationError(f"{key} must be a non-empty string")
    return value


def _require_literal(mapping: dict[str, Any], key: str, allowed: set[str]) -> str:
    value: str = _require_str(mapping, key)
    if value not in allowed:
        raise SpecValidationError(f"{key} must be one of {sorted(allowed)}")
    return value
