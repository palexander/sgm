# sgm

Spec-governed graph memory for coding agents.

## Development

```bash
uv sync --python 3.12 --extra dev
uv run pytest
uv run ty check
uv run ruff check
```

## Local State

```bash
rm -rf .sgm/
```

## CLI

```bash
uv run sgm --help
uv run sgm init
uv run sgm context specs/rpc-service-pattern.sgm.yaml
uv run sgm validate
uv run sgm validate --no-record
uv run sgm persist
```

`sgm` automatically refreshes file and spec state from disk on normal commands.
`sgm sync` remains available as an explicit debug/rebuild path.
Derived state is cached locally under `.sgm/work/state.json`.

`sgm init` bootstraps `specs/`, `decisions/`, `.sgm/work/`, and `.sgm/persisted/`,
ensures `.gitignore` excludes working state and persisted validation records, adds SGM guidance to `AGENTS.md`,
and updates `CLAUDE.md` when it already exists.

Repo spec files should use the naming convention `specs/{spec_name}.sgm.yaml`.

`sgm context <spec-file-or-id>` returns the full governing spec context plus all
files governed by that spec.

`sgm validate` validates all active specs against the current repo change set.
`sgm validate --no-record` is the dry run form.

`sgm context` and `sgm validate` surface a `[SPEC-DELTA]` unified diff on the
first run after a governing spec file changes on disk.

`sgm context` also surfaces active `[DECISIONS]` for files touched by
architectural or migration decisions, even when those files are not governed by
a behavioral spec.

When implementing a governed spec, the intended pattern is:
- the main agent orchestrates
- a sub-agent performs the implementation work
- modules should align to a single spec concern when practical so per-spec work and commits stay coherent

## Modularization Plan

The current code still crosses spec boundaries too often. The next structural pass
should reduce that overlap.

- Split [services.py](/Users/palexander/Developer/sgm/src/sgm/application/services.py) into focused application services such as context, validate, init, persist, and proposals.
- Split [models.py](/Users/palexander/Developer/sgm/src/sgm/domain/models.py) into smaller domain model modules grouped by spec-facing concern.
- Split [renderers.py](/Users/palexander/Developer/sgm/src/sgm/domain/renderers.py) into command-specific renderers so init, context, validate, and persist output evolve independently.
- Keep [cli.py](/Users/palexander/Developer/sgm/src/sgm/cli.py) thin and route command behavior into focused modules rather than growing one shared switchboard.
- Use spec splash radius as the default module boundary: if a change repeatedly spans multiple specs, prefer introducing a clearer module seam instead of broadening governance.

## Persistence Model

SGM separates durable repo artifacts from operational runtime state.

- Check into Git: `specs/`, `decisions/`, and other reviewable governance files.
- Keep out of Git: `.sgm/work/` caches, refresh indexes, locks, and validation
  records, plus `.sgm/persisted/validations/`.
- Persist durable proposal records into `.sgm/persisted/proposals/` with
  `uv run sgm persist` before commit or PR handoff.
- Keep proposals as the collaborative review record; keep routine validation
  runs in working state rather than promoting every run into Git.
