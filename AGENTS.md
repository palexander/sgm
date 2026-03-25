Use `sgm` when working in governed areas.

- Main agent: orchestrate spec work and hand implementation to a sub-agent.
- Prefer modules that align with a single spec concern so per-spec work and commits stay coherent.
- Before edits: `uv run sgm context <spec-file-or-id>`
- After edits: `uv run sgm validate`
- Dry run only: `uv run sgm validate --no-record`
- Before commit or handoff: `uv run sgm persist`
- If a touched file is ungoverned: `uv run sgm propose <spec-id> <path> "<reason>"`
