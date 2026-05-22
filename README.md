# sgm

Spec-governed graph memory for coding agents.

`sgm` helps a repo describe which behavior specs govern which files, then gives agents a focused workflow before and after edits. It keeps specs, decisions, proposals, delegation records, and coordination records reviewable while leaving transient runtime state local.

## Install and Update

Install the latest release:

```bash
curl -fsSL https://raw.githubusercontent.com/palexander/sgm/main/install.sh | bash
```

Install or pin a specific version:

```bash
SGM_VERSION=v0.1.1 curl -fsSL https://raw.githubusercontent.com/palexander/sgm/main/install.sh | bash
```

The installer uses `uv tool install --force`, so rerunning either command updates an existing install. If `sgm` is installed but not found on your shell path, add the `uv` tool bin directory printed by the installer to `PATH`.

## Getting Started

From the repo you want to govern:

```bash
sgm init
sgm spec add
```

`sgm init` creates the standard repo scaffolding, updates local ignore rules for SGM working state, and adds repo guidance for agents. `sgm spec add` creates a new behavior spec and opens it in your configured editor.

Write the behavior you want to govern in that spec, including the `governs` selectors for the files it owns. Commit the spec and generated guidance with the code or workflow it describes.

## Agent Workflow

Before an agent changes governed files, it should run:

```bash
sgm context <spec-file-or-id>
```

The context brief shows the active spec, any owner specs that must be read first, editable files, coordination files, relevant decisions, and next steps for unowned or owner-owned paths.

After edits, the agent should run:

```bash
sgm validate
```

Use `sgm validate --no-record` when you only want a dry run.

## Common Commands

```bash
sgm --help
sgm init
sgm spec add
sgm context <spec-file-or-id>
sgm validate
sgm validate --no-record
sgm shared list <spec-or-path>
sgm proposals list
sgm proposals review
```

`sgm` refreshes file and spec state from disk during normal commands. `sgm sync` remains available for explicit debug or rebuild work, but it is not part of the normal loop.

## Governance Model

Use the narrow behavior spec that matches the change. Current behavior specs cover the CLI command model, context and delta output, validation and focus, persistence, init bootstrap, and spec document format.

If a file is unowned, propose adding it to the active spec:

```bash
sgm propose <spec-id> <path> "<reason>"
```

If another active spec owns the file, ask a human first, then record standing shared access:

```bash
sgm shared allow <owner-spec-id> <spec-id> <path> "<reason>"
```

Coordination files are low-friction follow-through surfaces, such as command tables, README updates, registries, or shared smoke tests. They should accompany substantive in-scope work rather than become a way to bypass ownership.

## Stored State

Check durable governance artifacts into Git: `specs/`, `decisions/`, and reviewable records under `.sgm/persisted/`.

Keep operational state out of Git: `.sgm/work/` caches, indexes, locks, and validation records.

Proposal, delegation, and coordination records become durable when the relevant `sgm` command writes them. There is no separate persistence step in the normal workflow.
