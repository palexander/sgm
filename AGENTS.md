Use `sgm` when working in governed areas.

- Before edits: `uv run sgm context <path>`
- After edits: `uv run sgm validate <path>`
- Dry run only: `uv run sgm validate <path> --no-record`
- Before commit or handoff: `uv run sgm persist`
- If a touched file is ungoverned: `uv run sgm propose <spec-id> <path> "<reason>"`
