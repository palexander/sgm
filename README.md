# sgm

Spec-governed graph memory for coding agents.

## Development

```bash
uv sync --python 3.12 --extra dev
uv run pytest
uv run ty check
uv run ruff check
```

## Memgraph

```bash
docker run --rm -p 7687:7687 memgraph/memgraph:latest
```

## CLI

```bash
uv run sgm --help
uv run sgm validate src/services/discharge.ts
uv run sgm validate src/services/discharge.ts --no-record
```

`sgm` automatically refreshes file and spec state from disk on normal commands.
`sgm sync` remains available as an explicit debug/rebuild path.

`sgm context` and `sgm validate` surface a `[SPEC-DELTA]` unified diff on the
first run after a governing spec file changes on disk.
