from __future__ import annotations

from difflib import unified_diff

from sgm.domain.models import SpecDelta


def build_spec_delta(
    spec_id: str,
    source_path: str,
    previous_text: str | None,
    current_text: str,
    fallback_diff_lines: tuple[str, ...] | None = None,
) -> SpecDelta | None:
    if previous_text is None:
        if fallback_diff_lines is None:
            return None
        summary_lines, cleanup_required = summarize_spec_delta(fallback_diff_lines)
        return SpecDelta(
            spec_id=spec_id,
            source_path=source_path,
            diff_lines=fallback_diff_lines,
            current_exists=True,
            summary_lines=summary_lines,
            cleanup_required=cleanup_required,
        )
    if current_text == previous_text:
        return None

    diff_lines: tuple[str, ...] = tuple(
        unified_diff(
            previous_text.splitlines(),
            current_text.splitlines(),
            fromfile=f"a/{source_path}",
            tofile=f"b/{source_path}",
            lineterm="",
        )
    )
    summary_lines, cleanup_required = summarize_spec_delta(diff_lines)
    return SpecDelta(
        spec_id=spec_id,
        source_path=source_path,
        diff_lines=diff_lines,
        current_exists=True,
        summary_lines=summary_lines,
        cleanup_required=cleanup_required,
    )


def summarize_spec_delta(diff_lines: tuple[str, ...]) -> tuple[tuple[str, ...], bool]:
    added_behavior = 0
    removed_behavior = 0
    structural_changes = 0

    for line in diff_lines:
        if line.startswith(("---", "+++", "@@")):
            continue
        if _is_behavior_addition(line):
            added_behavior += 1
            continue
        if _is_behavior_removal(line):
            removed_behavior += 1
            continue
        if line.startswith("+") or line.startswith("-"):
            structural_changes += 1

    summary_lines: list[str] = []
    if added_behavior > 0:
        summary_lines.append(f"behavior added: {added_behavior} line(s)")
    if removed_behavior > 0:
        summary_lines.append(f"behavior removed: {removed_behavior} line(s)")
    if structural_changes > 0:
        summary_lines.append(f"structure or governance changed: {structural_changes} line(s)")
    if not summary_lines:
        summary_lines.append("spec text changed")
    return tuple(summary_lines), removed_behavior > 0


def _is_behavior_addition(line: str) -> bool:
    return line.startswith("+  ")


def _is_behavior_removal(line: str) -> bool:
    return line.startswith("-  ")
