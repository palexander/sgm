from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

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
from sgm.domain.renderers import (
    render_approval,
    render_context,
    render_init,
    render_persist,
    render_proposals,
    render_propose,
    render_rejection,
    render_sync_decision,
    render_sync_files,
    render_sync_spec,
    render_validation,
)

app = typer.Typer(help="Shared SGM CLI for humans and agents.")
proposals_app = typer.Typer(help="Review and manage governance proposals.")
sync_app = typer.Typer(help="Refresh derived graph state from repo sources.")
app.add_typer(proposals_app, name="proposals")
app.add_typer(sync_app, name="sync")


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
) -> None:
    _run_command(lambda service: _context(service, spec))


def _context(service: SgmService, spec: str) -> ExitCode:
    response = service.context(spec)
    typer.echo(render_context(response))
    return 0


@app.command(help="Validate active specs against the current repo change set.")
def validate(
    spec: Annotated[
        str | None,
        typer.Argument(
            help="Optional spec id, repo-relative spec path, or unique spec filename."
        ),
    ] = None,
    record: Annotated[
        bool,
        typer.Option(
            "--record/--no-record",
            help="Record validation state by default; use --no-record for a dry run.",
        ),
    ] = True,
) -> None:
    _run_command(lambda service: _validate(service, spec, record))


def _validate(service: SgmService, spec: str | None, record: bool) -> ExitCode:
    suite = service.validate(spec, record)
    typer.echo(render_validation(suite=suite, recorded=record))
    if any(report.error_files for report in suite.reports):
        return 2
    if any(report.warning_files for report in suite.reports):
        return 1
    return 0


@app.command(help="Propose governance for an ungoverned repo-relative path.")
def propose(
    spec_id: Annotated[str, typer.Argument(help="Spec identifier.")],
    path: Annotated[str, typer.Argument(help="Repo-relative path to govern.")],
    reason: Annotated[str, typer.Argument(help="Why this file should be governed.")],
) -> None:
    _run_command(lambda service: _propose(service, spec_id, path, reason))


def _propose(service: SgmService, spec_id: str, path: str, reason: str) -> ExitCode:
    typer.echo(render_propose(service.propose(spec_id, path, reason)))
    return 0


@app.command(help="Maintenance/debug command for legacy proposal records.")
def persist() -> None:
    _run_command(_persist, auto_refresh=False)


def _persist(service: SgmService) -> ExitCode:
    typer.echo(render_persist(service.persist()))
    return 0


@app.command(help="Bootstrap SGM files and guidance in the current repo.")
def init() -> None:
    _run_command(_init, auto_refresh=False)


def _init(service: SgmService) -> ExitCode:
    typer.echo(render_init(service.init()))
    return 0


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
