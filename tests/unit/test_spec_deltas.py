from __future__ import annotations

from sgm.domain.models import SpecDelta
from sgm.domain.render_shared import render_spec_delta
from sgm.domain.spec_deltas import build_spec_delta


def test_build_spec_delta_returns_none_when_text_is_unchanged() -> None:
    delta = build_spec_delta(
        spec_id="spec-001",
        source_path="specs/example.yaml",
        previous_text="version: 1\n",
        current_text="version: 1\n",
    )

    assert delta is None


def test_build_spec_delta_uses_fallback_diff_when_snapshot_is_missing() -> None:
    delta = build_spec_delta(
        spec_id="spec-001",
        source_path="specs/example.yaml",
        previous_text=None,
        current_text="version: 2\n",
        fallback_diff_lines=(
            "--- a/specs/example.yaml",
            "+++ b/specs/example.yaml",
            "@@ -1 +1 @@",
            "-version: 1",
            "+version: 2",
        ),
    )

    assert delta is not None
    assert delta.spec_id == "spec-001"
    assert delta.diff_lines[0] == "--- a/specs/example.yaml"
    assert delta.diff_lines[-1] == "+version: 2"
    assert "structure or governance changed: 2 line(s)" in delta.summary_lines
    assert delta.cleanup_required is False


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
    assert "structure or governance changed: 2 line(s)" in delta.summary_lines
    assert delta.cleanup_required is False


def test_build_spec_delta_marks_cleanup_when_behavior_lines_are_removed() -> None:
    delta = build_spec_delta(
        spec_id="spec-001",
        source_path="specs/example.yaml",
        previous_text="text: |\n  1. Old behavior\n",
        current_text="text: |\n  1. New behavior\n",
    )

    assert delta is not None
    assert "behavior added: 1 line(s)" in delta.summary_lines
    assert "behavior removed: 1 line(s)" in delta.summary_lines
    assert delta.cleanup_required is True


def test_render_spec_delta_includes_summary_without_cleanup() -> None:
    rendered = render_spec_delta(
        SpecDelta(
            spec_id="spec-001",
            source_path="specs/example.yaml",
            diff_lines=(
                "--- a/specs/example.yaml",
                "+++ b/specs/example.yaml",
                "@@ -1 +1,2 @@",
                " version: 1",
                "+status: active",
            ),
            current_exists=True,
            summary_lines=("behavior added: 1 line(s)",),
            cleanup_required=False,
        )
    )

    assert rendered[1] == "[DELTA-SUMMARY]"
    assert "behavior added: 1 line(s)" in rendered
    assert all("[CLEANUP]" not in line for line in rendered)


def test_render_spec_delta_includes_cleanup_when_behavior_is_removed() -> None:
    rendered = render_spec_delta(
        SpecDelta(
            spec_id="spec-001",
            source_path="specs/example.yaml",
            diff_lines=(
                "--- a/specs/example.yaml",
                "+++ b/specs/example.yaml",
                "@@ -1,2 +1 @@",
                " version: 1",
                "-status: active",
            ),
            current_exists=True,
            summary_lines=("behavior removed: 1 line(s)",),
            cleanup_required=True,
        )
    )

    assert rendered[1] == "[DELTA-SUMMARY]"
    assert "behavior removed: 1 line(s)" in rendered
    assert (
        "[CLEANUP] This spec removed behavior. Remove or isolate obsolete code, "
        "tests, and docs instead of keeping parallel implementations by default."
    ) in rendered
