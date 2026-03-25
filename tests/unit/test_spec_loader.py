from __future__ import annotations

from pathlib import Path

import pytest

from sgm.adapters.spec_loader import load_spec_document
from sgm.domain.errors import SpecValidationError


def test_load_spec_document_parses_valid_yaml(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.yaml"
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
                "assertions:",
                "  - id: assert-001",
                '    rule: "No direct DB imports"',
                "    hint: null",
                "    kind: structural",
                "    severity: error",
                "    check: file-import-deny",
                "    config:",
                '      deny: ["drizzle-orm"]',
                "governs:",
                '  - selector: "src/services/**"',
                "    priority: 1",
            ]
        ),
        encoding="utf-8",
    )

    document = load_spec_document(spec_path, tmp_path)

    assert document.id == "spec-001"
    assert document.source_path == "spec.yaml"
    assert "title: \"Service Pattern\"" in document.source_text
    assert document.warn_below == 0.8
    assert document.assertions[0].config["deny"] == ["drizzle-orm"]


def test_load_spec_document_rejects_invalid_config(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(
        "\n".join(
            [
                "id: spec-001",
                'title: "Service Pattern"',
                "version: 1",
                "status: active",
                "author: paul",
                'text: "Example"',
                "assertions:",
                "  - id: assert-001",
                '    rule: "No direct DB imports"',
                "    kind: structural",
                "    severity: error",
                "    check: file-import-deny",
                "    config:",
                '      deny: "drizzle-orm"',
                "governs: []",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SpecValidationError):
        load_spec_document(spec_path, tmp_path)
