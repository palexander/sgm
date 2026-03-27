Use `sgm` when working in governed areas.

- Main agent: orchestrate spec work and hand implementation to a sub-agent.
- Use the narrower behavior spec that matches the work: command model, context and delta, validation and focus, persistence, init, or spec format.
- Prefer modules that align with a single spec concern so per-spec work and commits stay coherent.
- Proposal records are durable immediately in `.sgm/persisted/proposals/`.
- Before edits: `uv run sgm context <spec-file-or-id>`
- After edits: `uv run sgm validate`
- Dry run only: `uv run sgm validate --no-record`
- If a touched file is ungoverned: `uv run sgm propose <spec-id> <path> "<reason>"`
