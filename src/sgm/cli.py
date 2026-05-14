from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import click
import typer

from sgm.adapters.filesystem import FileSystemAdapter
from sgm.adapters.repository import FileRepository
from sgm.adapters.system import SystemAdapter
from sgm.application.services import SgmService
from sgm.domain.errors import (
    EntityNotFoundError,
    FileNotFoundOnDiskError,
    InfrastructureError,
    NotIndexedError,
    RepoRootError,
    SgmError,
    SpecValidationError,
)
from sgm.domain.models import ExitCode, ProposalStatus
from sgm.domain.paths import ensure_repo_root
from sgm.domain.proposal_models import ProposalReviewItem
from sgm.domain.render_commands import render_proposal_review
from sgm.domain.renderers import (
    render_approval,
    render_context,
    render_coordination_mark,
    render_coordination_unmark,
    render_init,
    render_proposals,
    render_propose,
    render_rejection,
    render_shared_allow,
    render_shared_list,
    render_shared_revoke,
    render_sync_decision,
    render_sync_files,
    render_sync_spec,
    render_validation,
)

app = typer.Typer(help="Shared SGM CLI for humans and agents.")
proposals_app = typer.Typer(help="Review and manage governance proposals.")
spec_app = typer.Typer(help="Author and manage spec documents.")
shared_app = typer.Typer(help="Manage shared governance delegation and coordination.")
sync_app = typer.Typer(help="Refresh derived graph state from repo sources.")
hook_app = typer.Typer(help="Run agent hook entrypoints.")
app.add_typer(proposals_app, name="proposals")
app.add_typer(spec_app, name="spec")
app.add_typer(shared_app, name="shared")
app.add_typer(sync_app, name="sync")
app.add_typer(hook_app, name="hook")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


def _service() -> SgmService:
    repo_context = ensure_repo_root(Path.cwd())
    repository = FileRepository(repo_root=repo_context.root)
    filesystem = FileSystemAdapter(repo_root=repo_context.root)
    system = SystemAdapter()
    return SgmService(
        repo_context=repo_context,
        graph_repository=repository,
        filesystem=filesystem,
        system=system,
    )


@app.command(help="Show governing context for a spec id or repo-relative spec path.")
def context(
    spec: Annotated[
        str,
        typer.Argument(help="Spec id, repo-relative spec path, or unique spec filename."),
    ],
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Continue without focus warnings about unfinished work under other specs.",
        ),
    ] = False,
) -> None:
    _run_command(lambda service: _context(service, spec, force))


def _context(service: SgmService, spec: str, force: bool) -> ExitCode:
    response = service.context(spec, force=force)
    typer.echo(render_context(response))
    return 0


@app.command(help="Validate active specs against the current repo change set.")
def validate(
    spec: Annotated[
        str | None,
        typer.Argument(help="Optional spec id, repo-relative spec path, or unique spec filename."),
    ] = None,
    record: Annotated[
        bool,
        typer.Option(
            "--record/--no-record",
            help="Record validation state by default; use --no-record for a dry run.",
        ),
    ] = True,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Continue without focus warnings about unfinished work under other specs.",
        ),
    ] = False,
) -> None:
    _run_command(lambda service: _validate(service, spec, record, force))


def _validate(service: SgmService, spec: str | None, record: bool, force: bool) -> ExitCode:
    suite = service.validate(spec, record, force=force)
    typer.echo(render_validation(suite=suite, recorded=record))
    if any(report.error_files for report in suite.reports):
        return 2
    if any(report.warning_files or report.focus_warning is not None for report in suite.reports):
        return 1
    return 0


@app.command(help="Propose ownership expansion for an ungoverned repo-relative path.")
def propose(
    spec_id: Annotated[str, typer.Argument(help="Spec identifier.")],
    path: Annotated[str, typer.Argument(help="Repo-relative path to make owned by this spec.")],
    reason: Annotated[str, typer.Argument(help="Why ownership should expand to this file.")],
) -> None:
    _run_command(lambda service: _propose(service, spec_id, path, reason))


def _propose(service: SgmService, spec_id: str, path: str, reason: str) -> ExitCode:
    typer.echo(render_propose(service.propose(spec_id, path, reason)))
    return 0


@shared_app.command("allow", help="Record standing delegated access to an owner-owned file.")
def shared_allow(
    owner_spec_id: Annotated[str, typer.Argument(help="Owning spec identifier.")],
    delegate_spec_id: Annotated[str, typer.Argument(help="Delegate spec identifier.")],
    path: Annotated[str, typer.Argument(help="Repo-relative owned file path.")],
    reason: Annotated[str, typer.Argument(help="Why this delegated access is allowed.")],
) -> None:
    _run_command(
        lambda service: _shared_allow(service, owner_spec_id, delegate_spec_id, path, reason)
    )


def _shared_allow(
    service: SgmService,
    owner_spec_id: str,
    delegate_spec_id: str,
    path: str,
    reason: str,
) -> ExitCode:
    typer.echo(
        render_shared_allow(service.shared_allow(owner_spec_id, delegate_spec_id, path, reason))
    )
    return 0


@shared_app.command("revoke", help="Revoke delegated access to an owner-owned file.")
def shared_revoke(
    owner_spec_id: Annotated[str, typer.Argument(help="Owning spec identifier.")],
    delegate_spec_id: Annotated[str, typer.Argument(help="Delegate spec identifier.")],
    path: Annotated[str, typer.Argument(help="Repo-relative owned file path.")],
) -> None:
    _run_command(lambda service: _shared_revoke(service, owner_spec_id, delegate_spec_id, path))


def _shared_revoke(
    service: SgmService,
    owner_spec_id: str,
    delegate_spec_id: str,
    path: str,
) -> ExitCode:
    typer.echo(render_shared_revoke(service.shared_revoke(owner_spec_id, delegate_spec_id, path)))
    return 0


@shared_app.command(
    "mark-coordination",
    help="Mark an owner-owned file as coordination spillover for follow-through edits.",
)
def shared_mark_coordination(
    owner_spec_id: Annotated[str, typer.Argument(help="Owning spec identifier.")],
    path: Annotated[str, typer.Argument(help="Repo-relative owned file path.")],
    reason: Annotated[str, typer.Argument(help="Why this file is coordination spillover.")],
) -> None:
    _run_command(lambda service: _shared_mark_coordination(service, owner_spec_id, path, reason))


def _shared_mark_coordination(
    service: SgmService,
    owner_spec_id: str,
    path: str,
    reason: str,
) -> ExitCode:
    typer.echo(
        render_coordination_mark(service.shared_mark_coordination(owner_spec_id, path, reason))
    )
    return 0


@shared_app.command(
    "unmark-coordination",
    help="Remove coordination spillover status from an owner-owned file.",
)
def shared_unmark_coordination(
    owner_spec_id: Annotated[str, typer.Argument(help="Owning spec identifier.")],
    path: Annotated[str, typer.Argument(help="Repo-relative owned file path.")],
) -> None:
    _run_command(lambda service: _shared_unmark_coordination(service, owner_spec_id, path))


def _shared_unmark_coordination(
    service: SgmService,
    owner_spec_id: str,
    path: str,
) -> ExitCode:
    typer.echo(render_coordination_unmark(service.shared_unmark_coordination(owner_spec_id, path)))
    return 0


@shared_app.command("list", help="Show active delegation and coordination records.")
def shared_list(
    query: Annotated[
        str,
        typer.Argument(
            help="Spec id, spec path, unique spec filename, or repo-relative file path."
        ),
    ],
) -> None:
    _run_command(lambda service: _shared_list(service, query))


def _shared_list(service: SgmService, query: str) -> ExitCode:
    typer.echo(render_shared_list(service.shared_list(query)))
    return 0


@app.command(help="Bootstrap SGM files and guidance in the current repo.")
def init(
    hooks: Annotated[
        str,
        typer.Option(
            "--hooks",
            help="Optional agent hooks to install: none, claude, codex, or all.",
        ),
    ] = "none",
) -> None:
    _run_command(lambda service: _init(service, hooks), auto_refresh=False)


def _init(service: SgmService, hooks: str) -> ExitCode:
    normalized_hooks = hooks.strip().lower()
    if normalized_hooks not in {"none", "claude", "codex", "all"}:
        raise SgmError("--hooks must be one of: none, claude, codex, all")
    typer.echo(render_init(service.init(hooks=normalized_hooks)))
    return 0


@hook_app.command("pretool", help="Run the SGM PreToolUse hook.")
def hook_pretool() -> None:
    from sgm.hooks.pretool import main as run_hook

    raise typer.Exit(run_hook())


@hook_app.command("posttool", help="Run the SGM PostToolUse hook.")
def hook_posttool() -> None:
    from sgm.hooks.posttool import main as run_hook

    raise typer.Exit(run_hook())


@hook_app.command("stop", help="Run the SGM Stop hook.")
def hook_stop() -> None:
    from sgm.hooks.stop import main as run_hook

    raise typer.Exit(run_hook())


@hook_app.command(
    "semantic-reviewed",
    help="Record that the current agent performed the semantic alignment review.",
)
def hook_semantic_reviewed() -> None:
    from sgm.hooks.runtime import run_semantic_reviewed

    raise typer.Exit(run_semantic_reviewed())


@spec_app.command("add", help="Create a new spec file from a base template and open it.")
def spec_add() -> None:
    _run_command(_spec_add, auto_refresh=False)


def _spec_add(service: SgmService) -> ExitCode:
    spec_name = _prompt_spec_name()
    slug = _spec_slug(spec_name)
    spec_path = service.repo_context.root / "specs" / f"{slug}.sgm.yaml"
    repo_relative_path = spec_path.relative_to(service.repo_context.root).as_posix()
    if spec_path.exists():
        raise SgmError(f"spec file already exists: {repo_relative_path}")
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(_spec_template(spec_name, slug), encoding="utf-8")
    _open_editor(spec_path)
    typer.echo(f"[CREATED] {repo_relative_path}")
    return 0


def _prompt_spec_name() -> str:
    while True:
        spec_name = typer.prompt("Spec name").strip()
        if _spec_slug(spec_name) != "":
            return spec_name
        typer.echo("[ERROR] spec name must produce a non-empty slug")


def _spec_slug(spec_name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", spec_name.strip().lower())
    return normalized.strip("-")


def _spec_template(spec_name: str, slug: str) -> str:
    title_literal = json.dumps(spec_name)
    return (
        f"id: spec-{slug}-001\n"
        f"title: {title_literal}\n"
        "status: active\n"
        "author: TODO\n"
        "text: |\n"
        "  Describe the behavior this spec governs.\n"
        "governs: []\n"
    )


def _open_editor(path: Path) -> None:
    editor_command = _editor_command()
    try:
        subprocess.run([*editor_command, str(path)], check=True)
    except OSError as error:
        raise InfrastructureError(f"failed to open editor: {error}") from error
    except subprocess.CalledProcessError as error:
        raise InfrastructureError(f"editor exited with status {error.returncode}") from error


def _editor_command() -> list[str]:
    for variable_name in ("VISUAL", "EDITOR"):
        configured_editor = os.environ.get(variable_name, "").strip()
        if configured_editor == "":
            continue
        command = shlex.split(configured_editor)
        if command:
            return command
    raise InfrastructureError("no editor configured; set VISUAL or EDITOR")


@proposals_app.command("list", help="List governance proposals.")
def proposals_list(
    status: Annotated[
        ProposalStatus | None,
        typer.Option("--status", help="Filter by pending, approved, or rejected."),
    ] = None,
) -> None:
    _run_command(lambda service: _proposals_list(service, status))


def _proposals_list(service: SgmService, status: ProposalStatus | None) -> ExitCode:
    typer.echo(render_proposals(service.proposals_list(status)))
    return 0


@proposals_app.command("approve", help="Approve a governance proposal.")
def proposals_approve(
    proposal_id: Annotated[str, typer.Argument(help="Proposal identifier.")],
) -> None:
    _run_command(lambda service: _proposals_approve(service, proposal_id))


def _proposals_approve(service: SgmService, proposal_id: str) -> ExitCode:
    typer.echo(render_approval(service.proposals_approve(proposal_id)))
    return 0


@proposals_app.command("reject", help="Reject a governance proposal.")
def proposals_reject(
    proposal_id: Annotated[str, typer.Argument(help="Proposal identifier.")],
    reason: Annotated[str | None, typer.Option("--reason", help="Optional review reason.")] = None,
) -> None:
    _run_command(lambda service: _proposals_reject(service, proposal_id, reason))


def _proposals_reject(service: SgmService, proposal_id: str, reason: str | None) -> ExitCode:
    typer.echo(render_rejection(service.proposals_reject(proposal_id, reason)))
    return 0


@proposals_app.command("review", help="Review pending governance proposals interactively.")
def proposals_review() -> None:
    _run_command(_proposals_review)


def _proposals_review(service: SgmService) -> ExitCode:
    reviews = service.proposals_review().proposals
    if not reviews:
        typer.echo("[REVIEW] 0 pending proposals")
        return 0

    interactive = _is_tty_review()
    if not interactive:
        typer.echo(f"[REVIEW] {len(reviews)} pending proposals")
    for review_index, review in enumerate(reviews, start=1):
        expanded = False
        while True:
            if interactive:
                click.clear()
            typer.echo(
                _render_review_screen(
                    review=review,
                    review_index=review_index,
                    review_count=len(reviews),
                    expanded=expanded,
                    interactive=interactive,
                )
            )
            action, reason = _prompt_review_action()
            if action == "a":
                typer.echo(render_approval(service.proposals_approve(review.proposal.id)))
                break
            if action == "r":
                typer.echo(render_rejection(service.proposals_reject(review.proposal.id, reason)))
                break
            if action == "s":
                typer.echo(f"[SKIP] {review.proposal.id}")
                break
            if action == "g":
                expanded = True
                continue
            if action == "q":
                typer.echo("[REVIEW] quit")
                return 0
            if action == "?":
                typer.echo("[HELP] a=approve r[ reason]=reject s=skip g=files q=quit ?=help")
                continue
            typer.echo("[HELP] enter a, r, s, g, q, or ?")
    return 0


def _is_tty_review() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _render_review_screen(
    review: ProposalReviewItem,
    review_index: int,
    review_count: int,
    expanded: bool,
    interactive: bool,
) -> str:
    if interactive:
        lines: list[str] = [f"[REVIEW] {review_index}/{review_count} pending proposals", ""]
        height = _terminal_height()
        spec_excerpt_lines = _review_spec_excerpt_lines(
            review=review,
            expanded=expanded,
            height=height,
        )
    else:
        lines = []
        spec_excerpt_lines = None
    lines.extend(
        render_proposal_review(
            review,
            expanded=expanded,
            spaced=interactive,
            spec_excerpt_lines=spec_excerpt_lines,
        )
    )
    return "\n".join(lines)


def _terminal_height() -> int:
    return shutil.get_terminal_size(fallback=(80, 24)).lines


def _review_spec_excerpt_lines(review: ProposalReviewItem, expanded: bool, height: int) -> int:
    fixed_lines = 10
    if expanded:
        fixed_lines += len(review.governed_files) + 2
    available = height - fixed_lines
    if available < 1:
        return 1
    return available


def _prompt_review_action() -> tuple[str, str | None]:
    if _is_tty_review():
        return _prompt_review_action_tty()
    return _prompt_review_action_line()


def _prompt_review_action_tty() -> tuple[str, str | None]:
    typer.echo("Action [a/r/s/g/q/?]: ", nl=False)
    raw_action = click.getchar()
    typer.echo(raw_action)
    action = raw_action.strip().lower()[:1]
    if action != "r":
        return action, None
    try:
        reason = input("Reject reason (optional): ").strip()
    except EOFError:
        return "r", None
    return "r", reason or None


def _prompt_review_action_line() -> tuple[str, str | None]:
    try:
        raw_action = input("Action [a/r/s/g/q/?]: ")
    except EOFError:
        return "q", None
    stripped = raw_action.strip()
    normalized = stripped.lower()
    if (
        normalized in {"a", "approve"}
        or normalized.startswith("a ")
        or normalized.startswith("approve ")
    ):
        return "a", None
    if normalized in {"r", "reject"}:
        return "r", None
    if normalized.startswith("r "):
        return "r", stripped.split(" ", maxsplit=1)[1].strip() or None
    if normalized.startswith("reject "):
        return "r", stripped.split(" ", maxsplit=1)[1].strip() or None
    if normalized in {"s", "skip"} or normalized.startswith("s ") or normalized.startswith("skip "):
        return "s", None
    if normalized in {"g", "files", "governed"}:
        return "g", None
    if normalized in {"q", "quit"}:
        return "q", None
    if normalized in {"?", "help"}:
        return "?", None
    return normalized[:1], None


@sync_app.command("files", help="Scan files and refresh code-node state.")
def sync_files(
    path: Annotated[
        str | None,
        typer.Option("--path", help="Repo-relative directory to scan."),
    ] = None,
) -> None:
    _run_command(lambda service: _sync_files(service, path), auto_refresh=False)


def _sync_files(service: SgmService, path: str | None) -> ExitCode:
    typer.echo(render_sync_files(service.sync_files(path)))
    return 0


@sync_app.command("spec", help="Ingest a spec YAML file into the derived graph.")
def sync_spec(
    yaml_file: Annotated[str, typer.Argument(help="Spec YAML file to ingest.")],
) -> None:
    _run_command(lambda service: _sync_spec(service, yaml_file), auto_refresh=False)


def _sync_spec(service: SgmService, yaml_file: str) -> ExitCode:
    typer.echo(render_sync_spec(service.sync_spec(yaml_file)))
    return 0


@sync_app.command("decision", help="Ingest a decision YAML file into the derived graph.")
def sync_decision(
    yaml_file: Annotated[str, typer.Argument(help="Decision YAML file to ingest.")],
) -> None:
    _run_command(lambda service: _sync_decision(service, yaml_file), auto_refresh=False)


def _sync_decision(service: SgmService, yaml_file: str) -> ExitCode:
    typer.echo(render_sync_decision(service.sync_decision(yaml_file)))
    return 0


def _run_command(
    handler: Callable[[SgmService], ExitCode],
    auto_refresh: bool = True,
) -> None:
    try:
        service: SgmService = _service()
        if auto_refresh:
            service.refresh()
        exit_code: ExitCode = handler(service)
    except RepoRootError as error:
        typer.echo(f"[ERROR] {error}")
        raise typer.Exit(code=3) from error
    except FileNotFoundOnDiskError as error:
        typer.echo(f"[ERROR] {error}")
        raise typer.Exit(code=3) from error
    except NotIndexedError as error:
        typer.echo("[ERROR] target file missing from graph")
        raise typer.Exit(code=3) from error
    except SpecValidationError as error:
        typer.echo(f"[ERROR] {error}")
        raise typer.Exit(code=3) from error
    except EntityNotFoundError as error:
        typer.echo(f"[ERROR] {error}")
        raise typer.Exit(code=3) from error
    except InfrastructureError as error:
        typer.echo(f"[ERROR] {error}")
        raise typer.Exit(code=3) from error
    except SgmError as error:
        typer.echo(f"[ERROR] {error}")
        raise typer.Exit(code=3) from error
    raise typer.Exit(code=exit_code)


if __name__ == "__main__":
    app()
