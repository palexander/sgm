from __future__ import annotations

from sgm.domain.spec_deltas import build_spec_delta


def test_build_spec_delta_returns_none_when_text_is_unchanged() -> None:
    delta = build_spec_delta(
        spec_id="spec-001",
        source_path="specs/example.yaml",
        previous_text="version: 1\n",
        current_text="version: 1\n",
    )

    assert delta is None


def test_build_spec_delta_returns_unified_diff_for_changed_spec() -> None:
    delta = build_spec_delta(
        spec_id="spec-001",
        source_path="specs/example.yaml",
        previous_text="version: 1\n",
        current_text="version: 2\n",
    )

    assert delta is not None
    assert delta.spec_id == "spec-001"
    assert delta.current_exists is True
    assert "--- a/specs/example.yaml" in delta.diff_lines
    assert "+++ b/specs/example.yaml" in delta.diff_lines
    assert "-version: 1" in delta.diff_lines
    assert "+version: 2" in delta.diff_lines
