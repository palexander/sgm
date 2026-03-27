from __future__ import annotations

from pathlib import Path

import pytest

from sgm.adapters.spec_loader import load_spec_document
from sgm.domain.errors import SpecValidationError


def test_load_spec_document_parses_valid_yaml(tmp_path: Path) -> None:
    spec_path = tmp_path / "specs" / "spec.sgm.yaml"
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text(
        "\n".join(
            [
                "id: spec-001",
                'title: "Service Pattern"',
                "version: 1",
                "status: active",
                "author: paul",
                "text: |",
                "  Example",
                "governs:",
                '  - selector: "src/services/**"',
                "    priority: 1",
            ]
        ),
        encoding="utf-8",
    )

    document = load_spec_document(spec_path, tmp_path)

    assert document.id == "spec-001"
    assert document.source_path == "specs/spec.sgm.yaml"
    assert "title: \"Service Pattern\"" in document.source_text
    assert document.governs[0].selector == "src/services/**"


def test_load_spec_document_defaults_missing_governs_priority(tmp_path: Path) -> None:
    spec_path = tmp_path / "specs" / "spec.sgm.yaml"
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text(
        "\n".join(
            [
                "id: spec-001",
                'title: "Service Pattern"',
                "version: 1",
                "status: active",
                "author: paul",
                'text: "Example"',
                "governs:",
                '  - selector: "src/services/**"',
            ]
        ),
        encoding="utf-8",
    )

    document = load_spec_document(spec_path, tmp_path)

    assert document.governs[0].priority == 1


def test_load_spec_document_allows_missing_governs(tmp_path: Path) -> None:
    spec_path = tmp_path / "specs" / "overview.sgm.yaml"
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text(
        "\n".join(
            [
                "id: spec-001",
                'title: "Workflow Overview"',
                "version: 1",
                "status: deprecated",
                "author: paul",
                'text: "Overview only"',
            ]
        ),
        encoding="utf-8",
    )

    document = load_spec_document(spec_path, tmp_path)

    assert document.governs == ()


def test_load_spec_document_rejects_non_integer_governs_priority(tmp_path: Path) -> None:
    spec_path = tmp_path / "specs" / "spec.sgm.yaml"
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text(
        "\n".join(
            [
                "id: spec-001",
                'title: "Service Pattern"',
                "version: 1",
                "status: active",
                "author: paul",
                'text: "Example"',
                "governs:",
                '  - selector: "src/services/**"',
                "    priority: high",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SpecValidationError):
        load_spec_document(spec_path, tmp_path)
