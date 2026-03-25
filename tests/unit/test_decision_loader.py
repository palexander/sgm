from __future__ import annotations

from pathlib import Path

import pytest

from sgm.adapters.decision_loader import load_decision_document
from sgm.domain.errors import SpecValidationError


def test_load_decision_document_parses_valid_yaml(tmp_path: Path) -> None:
    decisions_dir = tmp_path / "decisions"
    decisions_dir.mkdir()
    decision_path = decisions_dir / "decision.yaml"
    decision_path.write_text(
        "\n".join(
            [
                "id: dec-001",
                'title: "Move off Memgraph"',
                "status: active",
                "context: |",
                "  Core workflows should stay local-first.",
                "decision: |",
                "  Replace Memgraph-backed storage with repo-local files.",
                "consequences: |",
                "  Adapter code and tests will change during migration.",
                "touches:",
                '  - selector: "src/sgm/**"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    document = load_decision_document(decision_path, tmp_path)

    assert document.id == "dec-001"
    assert document.source_path == "decisions/decision.yaml"
    assert document.touches[0].selector == "src/sgm/**"


def test_load_decision_document_rejects_invalid_touches(tmp_path: Path) -> None:
    decisions_dir = tmp_path / "decisions"
    decisions_dir.mkdir()
    decision_path = decisions_dir / "decision.yaml"
    decision_path.write_text(
        "\n".join(
            [
                "id: dec-001",
                'title: "Move off Memgraph"',
                "status: active",
                'context: "Context"',
                'decision: "Decision"',
                'consequences: "Consequences"',
                'touches: "src/sgm/**"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SpecValidationError):
        load_decision_document(decision_path, tmp_path)
