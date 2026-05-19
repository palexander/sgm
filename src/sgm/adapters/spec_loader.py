from __future__ import annotations

from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, cast

import yaml
from jsonschema import Draft202012Validator

from sgm.domain.errors import InfrastructureError, SpecValidationError
from sgm.domain.models import GovernanceSelector, SpecDocument, SpecStatus


def load_spec_document(path: Path, repo_root: Path) -> SpecDocument:
    source_text: str = path.read_text(encoding="utf-8")
    raw_document: object = yaml.safe_load(source_text)
    _validate_against_schema(raw_document)

    spec_mapping: dict[str, Any] = cast(dict[str, Any], raw_document)
    governs: list[GovernanceSelector] = []
    for governs_item in cast(list[dict[str, Any]], spec_mapping.get("governs", [])):
        governs.append(
            GovernanceSelector(
                selector=cast(str, governs_item["selector"]),
                priority=cast(int, governs_item.get("priority", 1)),
            )
        )

    return SpecDocument(
        id=cast(str, spec_mapping["id"]),
        source_path=path.resolve().relative_to(repo_root.resolve()).as_posix(),
        source_text=source_text,
        title=cast(str, spec_mapping["title"]),
        text=cast(str, spec_mapping["text"]),
        status=cast(SpecStatus, spec_mapping["status"]),
        author=cast(str, spec_mapping["author"]),
        governs=tuple(governs),
    )


def _validate_against_schema(raw_document: object) -> None:
    errors = sorted(_spec_validator().iter_errors(raw_document), key=str)
    if not errors:
        return
    raise SpecValidationError(_format_schema_error(errors[0]))


@lru_cache(maxsize=1)
def _spec_validator() -> Any:
    schema_path = Path(__file__).resolve().parents[3] / "specs" / "sgm-spec-document-format.yaml"
    try:
        schema_text = (
            resources.files("sgm")
            .joinpath("specs", "sgm-spec-document-format.yaml")
            .read_text(encoding="utf-8")
        )
    except OSError:
        try:
            schema_text = schema_path.read_text(encoding="utf-8")
        except OSError as error:
            raise InfrastructureError(f"failed to read spec schema: {error}") from error
    try:
        schema = yaml.safe_load(schema_text)
    except OSError as error:
        raise InfrastructureError(f"failed to read spec schema: {error}") from error
    if not isinstance(schema, dict):
        raise InfrastructureError("spec schema must contain a mapping")
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as error:
        raise InfrastructureError(f"spec schema is invalid: {error}") from error
    return Draft202012Validator(schema)


def _format_schema_error(error: Any) -> str:
    path = list(error.absolute_path)
    if not path:
        if error.validator == "type" and error.validator_value == "object":
            return "spec file must contain a mapping"
        if error.validator == "required":
            missing_key = error.message.split("'")[1]
            return f"{missing_key} must be a non-empty string"
    if path == ["governs"] and error.validator == "type":
        return "governs must be a list"
    if len(path) == 1 and error.validator == "required":
        missing_key = error.message.split("'")[1]
        return f"{missing_key} must be a non-empty string"
    if len(path) >= 1 and path[0] == "governs":
        if len(path) == 1 and error.validator == "type":
            return "each governs entry must be a mapping"
        if error.validator == "required":
            return "selector must be a non-empty string"
        if path[-1] == "selector":
            return "selector must be a non-empty string"
        if path[-1] == "priority":
            return "priority must be an integer"
    if path and error.validator == "type":
        key = str(path[-1])
        if error.validator_value == "integer":
            return f"{key} must be an integer"
        if error.validator_value == "string":
            return f"{key} must be a non-empty string"
    if path and error.validator == "minLength":
        return f"{path[-1]} must be a non-empty string"
    if path and error.validator == "enum":
        return f"{path[-1]} must be one of {sorted(cast(set[str], error.validator_value))}"
    return f"spec document does not match schema: {error.message}"
