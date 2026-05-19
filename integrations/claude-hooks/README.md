# Claude Hooks for SGM

This folder contains an optional Claude Code integration that nudges Claude to
follow the SGM workflow.

What it does:

- Adds a pre-work reminder when the user submits a prompt, if the host supports
  that hook event
- Requires `sgm context <spec>` before edits
- Blocks edits outside the active spec unless an explicit force override is set
- Prompts for a semantic spec-to-implementation alignment review before a task can stop
- Requires `sgm validate` after that review before a task can stop
- Stores hook state in `.sgm/work/claude-hook-state.json`

How to use it:

1. Copy the sample settings file from `.claude/settings.json` into your
   project’s Claude settings location.
2. Ensure the installed `sgm` binary is available on `PATH`.
3. Keep the generated wrapper commands pointed at `sgm hook pretool`,
   `sgm hook user-prompt`, `sgm hook posttool`, and `sgm hook stop`.

Notes:

- These hooks are best-effort guardrails, not a security boundary.
- If a checked-in hook config runs on a machine without `sgm` installed, the
  wrapper prints a warning and exits successfully instead of breaking the agent.
- The packaged runtime uses simple heuristics and a local state file so it stays
  easy to audit and adapt.
- The `PostToolUse` hook is included so successful `sgm context` and
  `sgm validate` commands can update state for later enforcement.
- When the stop hook asks for semantic alignment review, perform the review and
  run `sgm hook semantic-reviewed` before validating.
