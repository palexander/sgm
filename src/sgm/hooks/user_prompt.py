from __future__ import annotations

from sgm.hooks.runtime import run_user_prompt


def main() -> int:
    return run_user_prompt()


if __name__ == "__main__":
    raise SystemExit(main())
