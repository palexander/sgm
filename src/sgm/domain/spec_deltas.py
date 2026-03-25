from __future__ import annotations

from difflib import unified_diff

from sgm.domain.models import SpecDelta


def build_spec_delta(
    spec_id: str,
    source_path: str,
    previous_text: str | None,
    current_text: str,
) -> SpecDelta | None:
    if previous_text is None or current_text == previous_text:
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
    return SpecDelta(
        spec_id=spec_id,
        source_path=source_path,
        diff_lines=diff_lines,
        current_exists=True,
    )
