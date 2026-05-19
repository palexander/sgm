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
</sgm_instructions>
