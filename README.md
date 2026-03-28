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
uv run sgm context specs/context-and-delta.sgm.yaml
uv run sgm validate
uv run sgm validate --no-record
uv run sgm proposals review
```

`sgm` automatically refreshes file and spec state from disk on normal commands.
`sgm sync` remains available as an explicit debug/rebuild path.
Derived state is cached locally under `.sgm/work/state.json`.

`sgm init` bootstraps `specs/`, `decisions/`, `.sgm/work/`, and `.sgm/persisted/`,
ensures `.gitignore` excludes working state and persisted validation records, adds SGM guidance to `AGENTS.md`,
and updates `CLAUDE.md` when it already exists.

Repo spec files should use the naming convention `specs/{spec_name}.sgm.yaml`.

The old umbrella workflow spec has been retired as an enforcing spec. The
behavior is now split across narrower specs:
- `specs/cli-command-model.sgm.yaml`
- `specs/context-and-delta.sgm.yaml`
- `specs/validation-and-focus.sgm.yaml`
- `specs/persistence-artifacts.sgm.yaml`
- `specs/init-bootstrap.sgm.yaml`
- `specs/spec-document-format.sgm.yaml`

`sgm context <spec-file-or-id>` returns the full governing spec context plus all
files governed by that spec.

`sgm validate` validates all active specs against the current repo change set.
`sgm validate --no-record` is the dry run form.

`sgm context` and `sgm validate` surface a `[SPEC-DELTA]` unified diff on the
first run after a governing spec file changes on disk.

`sgm context` also surfaces active `[DECISIONS]` for files touched by
architectural or migration decisions, even when those files are not governed by
a behavioral spec.

`sgm proposals review` walks pending proposals one at a time in deterministic
order. Use `a` to approve, `r` to reject, `s` to skip, and `g` to expand the
current prompt with the governed files for the target spec. In a real terminal,
those actions work as single-key input; piped and test runs fall back to
line-based input.

When implementing a governed spec, the intended pattern is:
- the main agent orchestrates
- a sub-agent performs the implementation work
- modules should align to a single spec concern when practical so per-spec work and commits stay coherent
- agents should not edit spec files directly during implementation
- incidental splash expansion should go through `uv run sgm propose`

## Human Workflow

- Write or update the spec under `specs/` that matches the behavior you are changing.
- Use the narrower behavior specs rather than the retired umbrella workflow spec.
- Define the spec's initial `governs` selectors.
- During implementation, do not edit spec files directly; use `sgm propose` if a change needs incidental splash expansion.
- Run `uv run sgm validate` to see whether the current repo state is valid across active specs, or `uv run sgm validate <spec>` for one spec.
- Review pending governance expansions with `uv run sgm proposals list`.
- Approve or reject proposals as part of review with `uv run sgm proposals approve <proposal-id>` or `uv run sgm proposals reject <proposal-id>`.
- Use `uv run sgm proposals review` when you want to step through pending proposals interactively.

## Persistence Model

SGM separates durable repo artifacts from operational runtime state.

- Check into Git: `specs/`, `decisions/`, and other reviewable governance files.
- Keep out of Git: `.sgm/work/` caches, refresh indexes, locks, and validation
  records.
- Proposal records are durable immediately in `.sgm/persisted/proposals/` when
  you create, approve, or reject them.
- Keep proposals as the collaborative review record; keep routine validation
  runs in working state rather than promoting every run into Git.
