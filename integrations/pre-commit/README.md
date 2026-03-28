# Pre-commit for SGM

This folder contains an optional pre-commit integration for SGM.

It is the final gate, not the live workflow layer:
- Claude hooks steer agents while they work.
- Pre-commit checks the repo state before it is recorded.

What it does:
- Runs `sgm validate --no-record`
- Fails the commit on validation errors
- Can allow warning-only status when you opt in

How to use it:
1. Copy the sample config from `.pre-commit-config.yaml` into your repo.
2. Point it at `integrations/pre-commit/bin/validate.py`.
3. Keep strict mode as the default. Use warning mode only when you want an explicit exception.

Modes:
- Strict mode is the default and blocks on warnings or failures.
- Warn mode can be enabled with `--allow-warn` or `SGM_PRECOMMIT_ALLOW_WARN=1`.

Tradeoffs:
- Good for humans, editors, and any agent that bypasses Claude hooks.
- Not a substitute for interactive workflow guidance.
- It only sees the repo at commit time, so it cannot nudge mid-task behavior.
