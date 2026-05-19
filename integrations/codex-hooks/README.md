# Codex Hooks for SGM

This folder contains an optional Codex integration that runs the packaged SGM
hook runtime from repo-local hooks.

What it does:

- Adds a pre-work reminder when the user submits a prompt, if the host supports
  that hook event
- Requires `sgm context <spec>` before governed edits
- Blocks edits outside the active spec unless an explicit force override is set
- Prompts for a semantic spec-to-implementation alignment review before a task can stop
- Requires `sgm validate` after that review before a task can stop when edits are dirty
- Stores hook state in `.sgm/work/claude-hook-state.json` for compatibility

How to use it:

1. Copy the sample hooks file from `.codex/hooks.json` into your project's
   repo-local Codex hooks location.
2. Ensure the installed `sgm` binary is available on `PATH`.
3. Keep the generated wrapper commands pointed at `sgm hook pretool`,
   `sgm hook user-prompt`, `sgm hook posttool`, and `sgm hook stop`.

Payload support:

- Command payloads may use `tool_input.command`, `tool_input.cmd`, top-level
  `command`, or top-level `cmd`.
- The working directory comes from top-level `cwd` when present.
- Event names may use top-level `hook_event_name`.

Notes:

- These hooks are best-effort guardrails, not a security boundary.
- If a checked-in hook config runs on a machine without `sgm` installed, the
  wrapper prints a warning and exits successfully instead of breaking the agent.
- The shared runtime intentionally keeps the Claude-compatible state file name
  so existing local hook state continues to work.
- When the stop hook asks for semantic alignment review, perform the review and
  run `sgm hook semantic-reviewed` before validating.
