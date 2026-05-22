<sgm_instructions>
Use `sgm` when working in governed areas.

- Main agent: orchestrate spec work and hand implementation to a sub-agent.
- Use the narrower behavior spec that matches the work: command model, context and delta, validation and focus, persistence, init, or spec format.
- Prefer modules that align with a single spec concern so per-spec work and commits stay coherent.
- Do not edit spec files directly during implementation; use `sgm propose` for incidental splash expansion.
- Proposal records are durable immediately in `.sgm/persisted/proposals/`.
- If a touched file is unowned: `sgm propose <spec-id> <path> "<reason>"`.
- If another spec owns the file: ask a human, then record `sgm shared allow <owner-spec-id> <spec-id> <path> "<reason>"`.
- On delegated shared files, the owner spec wins.
- Coordination files are only for mechanical follow-through alongside substantive editable work.
- Before edits: `sgm context <spec-file-or-id>`
- After edits: `sgm validate`
- Dry run only: `sgm validate --no-record`

Governed workflow details:

- `sgm init` bootstraps `specs/`, `decisions/`, `.sgm/work/`, `.sgm/persisted/`, repo ignore rules, and repo-local agent guidance.
- Use `sgm spec add` for new behavior specs; it creates `specs/{spec-name}.sgm.yaml` and opens it in the configured editor.
- Treat `sgm sync` as a debug/rebuild command, not a normal prerequisite.
- Use `sgm shared mark-coordination <owner-spec-id> <path> "<reason>"` for low-friction spillover files such as registries, command tables, README updates, and shared smoke tests.
- Use `sgm shared list <spec-or-path>` to inspect current ownership, delegation, and coordination records.
- Use `sgm proposals list` or `sgm proposals review` to inspect pending ownership expansions.

Persistence model:

- Check durable governance artifacts into Git: `specs/`, `decisions/`, and reviewable records under `.sgm/persisted/`.
- Keep operational state out of Git: `.sgm/work/` caches, indexes, locks, and validation records.
- Proposal, delegation, and coordination records are durable when the relevant command writes them; do not add a separate persistence step to the normal workflow.

Local development commands:

- Install dev dependencies with `uv sync --python 3.12 --extra dev`.
- Run tests with `uv run pytest`.
- Run type checks with `uv run ty check`.
- Run lint checks with `uv run ruff check`.
- Remove local SGM state with `rm -rf .sgm/` only when deliberately resetting derived state for this repo.
</sgm_instructions>
