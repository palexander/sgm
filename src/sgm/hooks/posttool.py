from __future__ import annotations

from sgm.hooks.runtime import run_posttool


def main() -> int:
    return run_posttool()


if __name__ == "__main__":
    raise SystemExit(main())

