from __future__ import annotations

from sgm.domain.spec_models import SpecDelta


def render_spec_delta(spec_delta: SpecDelta) -> list[str]:
    status_suffix: str = (
        "changed since last ingest"
        if spec_delta.current_exists
        else "was removed since last ingest"
    )
    lines: list[str] = [
        f"[SPEC-DELTA] {spec_delta.spec_id} {spec_delta.source_path} {status_suffix}",
    ]
    if spec_delta.summary_lines:
        lines.append("[DELTA-SUMMARY]")
        lines.extend(spec_delta.summary_lines)
    lines.extend(spec_delta.diff_lines)
    if spec_delta.cleanup_required:
        lines.append(
            "[CLEANUP] This spec removed behavior. Remove or isolate "
            "obsolete code, tests, and docs instead of keeping parallel "
            "implementations by default."
        )
    return lines
