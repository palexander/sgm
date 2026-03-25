from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from sgm.adapters.config import load_graph_connection_config
from sgm.adapters.filesystem import FileSystemAdapter
from sgm.adapters.memgraph import MemgraphRepository
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
    render_proposals,
    render_propose,
    render_rejection,
    render_sync_files,
    render_sync_spec,
    render_validation,
)

app = typer.Typer(help="Spec-governed graph memory CLI.")
proposals_app = typer.Typer(help="Manage governance proposals.")
sync_app = typer.Typer(help="Synchronize graph state from repo sources.")
app.add_typer(proposals_app, name="proposals")
app.add_typer(sync_app, name="sync")


def _service() -> SgmService:
    repo_context = ensure_repo_root(Path.cwd())
    repository = MemgraphRepository(config=load_graph_connection_config())
    filesystem = FileSystemAdapter(repo_root=repo_context.root)
    system = SystemAdapter()
    return SgmService(
        repo_context=repo_context,
        graph_repository=repository,
        filesystem=filesystem,
        system=system,
    )


@app.command()
def context(
    path: Annotated[str, typer.Argument(help="Repo-relative path to inspect.")],
) -> None:
    _run_command(lambda service: _context(service, path))


def _context(service: SgmService, path: str) -> ExitCode:
    response = service.context(path)
    typer.echo(render_context(response))
    return 0


@app.command()
def validate(
    path: Annotated[str, typer.Argument(help="Repo-relative path to validate.")],
    record: Annotated[
        bool,
        typer.Option(
            "--record/--no-record",
            help="Record compliance state by default; use --no-record for a dry run.",
        ),
    ] = True,
) -> None:
    _run_command(lambda service: _validate(service, path, record))


def _validate(service: SgmService, path: str, record: bool) -> ExitCode:
    report, previous_scores, updated_scores = service.validate(path, record)
    typer.echo(
        render_validation(
            report=report,
            recorded=record,
            previous_scores=previous_scores,
            updated_scores=updated_scores,
        )
    )
    if not report.spec_summaries:
        return 0
    has_error: bool = any(summary.failed_errors > 0 for summary in report.spec_summaries)
    has_warning: bool = any(summary.failed_warnings > 0 for summary in report.spec_summaries)
    if has_error:
        return 2
    if has_warning:
        return 1
    return 0


@app.command()
def propose(
    spec_id: Annotated[str, typer.Argument(help="Spec identifier.")],
    path: Annotated[str, typer.Argument(help="Repo-relative path to govern.")],
    reason: Annotated[str, typer.Argument(help="Why this file should be governed.")],
) -> None:
    _run_command(lambda service: _propose(service, spec_id, path, reason))


def _propose(service: SgmService, spec_id: str, path: str, reason: str) -> ExitCode:
    typer.echo(render_propose(service.propose(spec_id, path, reason)))
    return 0


@proposals_app.command("list")
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


@proposals_app.command("approve")
def proposals_approve(
    proposal_id: Annotated[str, typer.Argument(help="Proposal identifier.")],
) -> None:
    _run_command(lambda service: _proposals_approve(service, proposal_id))


def _proposals_approve(service: SgmService, proposal_id: str) -> ExitCode:
    typer.echo(render_approval(service.proposals_approve(proposal_id)))
    return 0


@proposals_app.command("reject")
def proposals_reject(
    proposal_id: Annotated[str, typer.Argument(help="Proposal identifier.")],
    reason: Annotated[str | None, typer.Option("--reason", help="Optional review reason.")] = None,
) -> None:
    _run_command(lambda service: _proposals_reject(service, proposal_id, reason))


def _proposals_reject(service: SgmService, proposal_id: str, reason: str | None) -> ExitCode:
    typer.echo(render_rejection(service.proposals_reject(proposal_id, reason)))
    return 0


@sync_app.command("files")
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


@sync_app.command("spec")
def sync_spec(
    yaml_file: Annotated[str, typer.Argument(help="Spec YAML file to ingest.")],
) -> None:
    _run_command(lambda service: _sync_spec(service, yaml_file), auto_refresh=False)


def _sync_spec(service: SgmService, yaml_file: str) -> ExitCode:
    typer.echo(render_sync_spec(service.sync_spec(yaml_file)))
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
