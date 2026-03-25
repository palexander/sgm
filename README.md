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
uv run sgm validate src/services/discharge.ts
uv run sgm validate src/services/discharge.ts --no-record
uv run sgm persist
```

`sgm` automatically refreshes file and spec state from disk on normal commands.
`sgm sync` remains available as an explicit debug/rebuild path.
Derived state is cached locally under `.sgm/work/state.json`.

`sgm context` and `sgm validate` surface a `[SPEC-DELTA]` unified diff on the
first run after a governing spec file changes on disk.

`sgm context` also surfaces active `[DECISIONS]` for files touched by
architectural or migration decisions, even when those files are not governed by
a behavioral spec.

## Persistence Model

SGM separates durable repo artifacts from operational runtime state.

- Check into Git: `specs/`, `decisions/`, and other reviewable governance files.
- Keep out of Git: `.sgm/work/` caches, refresh indexes, locks, and per-run
  working records.
- Persist durable records into `.sgm/persisted/` with `uv run sgm persist`
  before commit or PR handoff.
- Prefer file-per-item or append-only shared artifacts in `.sgm/persisted/`
  over a single mutable state file when collaboration needs durable history.
