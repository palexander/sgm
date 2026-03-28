#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run sgm validate as a pre-commit gate.")
    parser.add_argument(
        "--allow-warn",
        action="store_true",
        help="Allow warning-only validation results.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    allow_warn = args.allow_warn or os.environ.get("SGM_PRECOMMIT_ALLOW_WARN") == "1"

    result = subprocess.run(
        ["sgm", "validate", "--no-record"],
        check=False,
        text=True,
        capture_output=True,
    )

    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)

    output = f"{result.stdout}\n{result.stderr}"
    has_warn = "[WARN]" in output
    has_fail = "[FAIL]" in output or result.returncode not in (0, 1, 2)

    if has_fail:
        return result.returncode or 1
    if has_warn and not allow_warn:
        return 1
    if result.returncode != 0 and not has_warn:
        return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
