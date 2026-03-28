# Claude Hooks for SGM

This folder contains an optional Claude Code integration that nudges Claude to
follow the SGM workflow.

What it does:

- Requires `sgm context <spec>` before edits
- Blocks edits outside the active spec unless an explicit force override is set
- Requires `sgm validate` before a task can stop
- Stores hook state in `.sgm/work/claude-hook-state.json`

How to use it:

1. Copy the sample settings file from `.claude/settings.json` into your
   project’s Claude settings location.
2. Keep the helper scripts in `integrations/claude-hooks/bin/`.
3. Run `sgm init` or create `.sgm/work/` so the hook state path exists.

Notes:

- These hooks are best-effort guardrails, not a security boundary.
- The sample scripts use simple heuristics and a local state file so they stay
  easy to audit and adapt.
- The `PostToolUse` hook is included so successful `sgm context` and
  `sgm validate` commands can update state for later enforcement.
