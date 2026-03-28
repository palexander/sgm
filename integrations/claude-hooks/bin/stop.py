#!/usr/bin/env python3
from __future__ import annotations

import json
import sys

from _common import load_state, project_root


def block(reason: str) -> int:
    json.dump({"decision": "block", "reason": reason}, sys.stdout)
    sys.stdout.write("\n")
    return 0


def allow() -> int:
    return 0


def main() -> int:
    payload = json.load(sys.stdin)
    cwd = project_root(payload)
    state = load_state(cwd)

    if state.force_override:
        return allow()

    if state.dirty_since_validate:
        return block(
            "SGM still has unvalidated edits in the current spec scope. "
            "Run `sgm validate` before finishing, or use `--force` if you "
            "intentionally want to stop early."
        )

    return allow()


if __name__ == "__main__":
    raise SystemExit(main())
