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
uv run sgm spec add
uv run sgm context specs/context-and-delta.sgm.yaml
uv run sgm validate
uv run sgm validate --no-record
uv run sgm shared list specs/context-and-delta.sgm.yaml
uv run sgm proposals review
```

`sgm` automatically refreshes file and spec state from disk on normal commands.
`sgm sync` remains available as an explicit debug/rebuild path.
Derived state is cached locally under `.sgm/work/state.json`.

`sgm init` bootstraps `specs/`, `decisions/`, `.sgm/work/`, and `.sgm/persisted/`,
ensures `.gitignore` excludes working state and persisted validation records, adds SGM guidance to `AGENTS.md`,
and updates `CLAUDE.md` when it already exists.

Repo spec files should use the naming convention `specs/{spec_name}.sgm.yaml`.
`uv run sgm spec add` prompts for a spec name, creates a starter spec file, and opens it in your configured editor.

The old umbrella workflow spec has been retired as an enforcing spec. The
behavior is now split across narrower specs:
- `specs/cli-command-model.sgm.yaml`
- `specs/context-and-delta.sgm.yaml`
- `specs/validation-and-focus.sgm.yaml`
- `specs/persistence-artifacts.sgm.yaml`
- `specs/init-bootstrap.sgm.yaml`
- `specs/spec-document-format.sgm.yaml`

`sgm context <spec-file-or-id>` returns a self-contained brief with:
- `[TARGET]` for the active spec
- `[READ]` for any owner specs that must be consulted first
- `[EDITABLE]` for owned and delegated files
- `[COORDINATION]` for spillover files that are only allowed alongside substantive in-scope work
- `[NEXT]` for the exact next command when the file is unowned or owned by another spec

`sgm validate` validates all active specs against the current repo change set.
`sgm validate --no-record` is the dry run form.

`sgm shared allow` records standing owner-delegate access for a whole file without
changing ownership. `sgm shared mark-coordination` records a low-friction
follow-through surface such as a command table, README, or shared smoke test.

`sgm context` and `sgm validate` surface a `[SPEC-DELTA]` unified diff on the
first run after a governing spec file changes on disk.

`sgm context` also surfaces active `[DECISIONS]` for files touched by
architectural or migration decisions, even when those files are not governed by
a behavioral spec.

`sgm proposals review` walks pending proposals one at a time in deterministic
order. Use `a` to approve, `r` to reject, `s` to skip, and `g` to expand the
current prompt with the governed files for the target spec. In a real terminal,
the review screen redraws from the top between items so each proposal gets an
uncluttered view. The prompt sizes the spec excerpt to the visible terminal
height and keeps extra blank space before the key hints so the controls do not
blend into the spec text. Piped and test runs fall back to line-based input and
keep a plain transcript.

When implementing a governed spec, the intended pattern is:
- the main agent orchestrates
- a sub-agent performs the implementation work
- modules should align to a single spec concern when practical so per-spec work and commits stay coherent
- agents should not edit spec files directly during implementation
- use `uv run sgm propose` only for unowned files that should become owned by the active spec
- if another spec already owns the file, ask a human and record `uv run sgm shared allow`
- on delegated shared files, the owner spec wins
- coordination files are only for follow-through alongside substantive editable work

## Human Workflow

- Write or update the spec under `specs/` that matches the behavior you are changing.
- Use the narrower behavior specs rather than the retired umbrella workflow spec.
- Define the spec's initial `governs` selectors.
- During implementation, do not edit spec files directly; use `sgm propose` only when an unowned file should become owned by the active spec.
- If another active spec owns the file, keep ownership where it is and record a standing grant with `uv run sgm shared allow <owner-spec-id> <spec-id> <path> "<reason>"`.
- Use `uv run sgm shared mark-coordination <owner-spec-id> <path> "<reason>"` for low-friction spillover files such as registries, command tables, docs, and shared smoke tests.
- Run `uv run sgm validate` to see whether the current repo state is valid across active specs, or `uv run sgm validate <spec>` for one spec.
- Use `uv run sgm shared list <spec-or-path>` to inspect current owner, delegation, and coordination records.
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
- Delegation records are durable immediately in `.sgm/persisted/delegations/`.
- Coordination records are durable immediately in `.sgm/persisted/coordination/`.
- Keep proposals as the collaborative review record; keep routine validation
  runs in working state rather than promoting every run into Git.
