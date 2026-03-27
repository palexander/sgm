from __future__ import annotations

from sgm.domain.models import FocusWarning, GoverningSpec, RelatedDecision, SpecContextResponse
from sgm.domain.render_shared import render_proposal, render_spec_delta


def render_context(response: SpecContextResponse) -> str:
    lines: list[str] = ["[SPEC] 1 governing"]
    lines.extend(_render_governing_spec(spec=response.spec))

    if response.focus_warning is not None:
        lines.append("")
        lines.extend(_render_focus_warning(response.focus_warning))

    if response.governed_files:
        lines.append("")
        lines.append(f"[FILES] {len(response.governed_files)} governed")
        lines.extend(response.governed_files)

    if response.pending_proposals:
        lines.append("")
        lines.append(f"[PROPOSALS] {len(response.pending_proposals)} pending")
        for proposal in response.pending_proposals:
            lines.extend(render_proposal(proposal=proposal))

    if response.decisions:
        lines.append("")
        lines.append(f"[DECISIONS] {len(response.decisions)} informing")
        for decision in response.decisions:
            lines.extend(_render_related_decision(decision=decision))
            lines.append("")
        while lines and lines[-1] == "":
            lines.pop()
    return "\n".join(lines)


def _render_governing_spec(spec: GoverningSpec) -> list[str]:
    lines: list[str] = [f"{spec.id} v{spec.version} {spec.title} (priority={spec.priority})"]
    for text_line in spec.text.strip().splitlines():
        lines.append(f"  {text_line}")
    if spec.spec_delta is not None:
        lines.extend(render_spec_delta(spec.spec_delta))
    return lines


def _render_related_decision(decision: RelatedDecision) -> list[str]:
    lines: list[str] = [f"{decision.id} {decision.title} [{decision.status}]"]
    for text_line in decision.context.strip().splitlines():
        lines.append(f"  context: {text_line}")
    for text_line in decision.decision.strip().splitlines():
        lines.append(f"  decision: {text_line}")
    for text_line in decision.consequences.strip().splitlines():
        lines.append(f"  consequences: {text_line}")
    return lines


def _render_focus_warning(focus_warning: FocusWarning) -> list[str]:
    lines: list[str] = [
        (
            "[FOCUS-WARN] "
            f"unfinished governed work exists under {len(focus_warning.conflicts)} "
            "other spec(s)"
        )
    ]
    for conflict in focus_warning.conflicts:
        lines.append(f"{conflict.spec_id} {conflict.source_path}")
        for path in conflict.changed_files:
            lines.append(f"  pending: {path}")
    lines.append("Use --force to continue anyway.")
    return lines
