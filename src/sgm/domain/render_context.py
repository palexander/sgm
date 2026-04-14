from __future__ import annotations

from sgm.domain.models import (
    FocusWarning,
    ReadRequirement,
    RelatedDecision,
    SpecContextResponse,
)
from sgm.domain.render_commands import render_proposal
from sgm.domain.render_shared import render_spec_delta


def render_context(response: SpecContextResponse) -> str:
    lines: list[str] = ["[TARGET]"]
    lines.extend(_render_target(response))

    if response.read_specs:
        lines.append("")
        lines.append(f"[READ] {len(response.read_specs)} specs")
        for index, requirement in enumerate(_ordered_read_specs(response.read_specs), start=1):
            lines.extend(_render_read_requirement(index=index, requirement=requirement))

    lines.append("")
    lines.append(f"[EDITABLE] {len(response.editable_files)} files")
    lines.extend(response.editable_files)

    if response.coordination_files:
        lines.append("")
        lines.append(f"[COORDINATION] {len(response.coordination_files)} files")
        for coordination in response.coordination_files:
            lines.append(f"{coordination.path} <- {coordination.owner_spec_id}")
        lines.append(
            "Only use coordination files as follow-through when this change already touches a substantive editable file."
        )

    if response.pending_proposals:
        lines.append("")
        lines.append(f"[PROPOSALS] {len(response.pending_proposals)} pending")
        for proposal in response.pending_proposals:
            lines.extend(render_proposal(proposal=proposal))

    if response.decisions:
        lines.append("")
        lines.append(f"[DECISIONS] {len(response.decisions)} informing")
        for decision in response.decisions:
            lines.extend(_render_related_decision(decision))
            lines.append("")
        while lines and lines[-1] == "":
            lines.pop()

    if response.next_steps:
        lines.append("")
        lines.append("[NEXT]")
        lines.extend(f"- {step}" for step in response.next_steps)

    if response.focus_warning is not None:
        lines.append("")
        lines.extend(_render_focus_warning(response.focus_warning))

    return "\n".join(lines)


def _render_target(response: SpecContextResponse) -> list[str]:
    spec = response.spec
    lines = [
        f"{spec.id} {spec.title} (priority={spec.priority})",
        f"source: {spec.source_path}",
    ]
    for text_line in spec.text.strip().splitlines():
        lines.append(f"  {text_line}")
    if spec.spec_delta is not None:
        lines.extend(render_spec_delta(spec.spec_delta))
    return lines


def _ordered_read_specs(read_specs: tuple[ReadRequirement, ...]) -> tuple[ReadRequirement, ...]:
    owners = tuple(requirement for requirement in read_specs if requirement.role == "owner")
    targets = tuple(requirement for requirement in read_specs if requirement.role == "target")
    return owners + targets


def _render_read_requirement(index: int, requirement: ReadRequirement) -> list[str]:
    spec = requirement.spec
    if requirement.role == "owner":
        paths = ", ".join(requirement.paths)
        header = f"{index}. {spec.id} [owner for {paths}]"
        guidance = "Read this before editing those shared files. If it disagrees, the owner wins."
    else:
        header = f"{index}. {spec.id} [target]"
        guidance = "This is the active task spec."
    lines = [header, f"   source: {spec.source_path}", f"   {guidance}"]
    for text_line in spec.text.strip().splitlines():
        lines.append(f"   {text_line}")
    if spec.spec_delta is not None:
        lines.extend(f"   {line}" for line in render_spec_delta(spec.spec_delta))
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
    lines = [
        "[FOCUS-WARN]",
        (
            f"Unfinished editable work exists under {len(focus_warning.conflicts)} "
            "other spec(s). Use --force to continue anyway."
        ),
    ]
    for conflict in focus_warning.conflicts:
        lines.append(f"{conflict.spec_id} {conflict.source_path}")
        for path in conflict.changed_files:
            lines.append(f"  pending: {path}")
    return lines
