#!/usr/bin/env python3
"""Record a reusable lesson, validate the skill, and sync the GitHub mirror."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True, help="Demo, session, or lesson title")
    parser.add_argument("--date", help="Entry date, YYYY-MM-DD")
    parser.add_argument("--source", action="append", required=True, help="Observed source pattern")
    parser.add_argument("--issue", action="append", required=True, help="Issue or migration gap")
    parser.add_argument(
        "--replacement",
        action="append",
        required=True,
        help="Verified Huawei replacement or demo-safe approximation",
    )
    parser.add_argument("--validation", action="append", required=True, help="Validation evidence")
    parser.add_argument("--message", help="Git commit message for the mirror update")
    args = parser.parse_args()

    scripts_dir = Path(__file__).resolve().parent
    append_script = scripts_dir / "append_demo_lesson.py"
    sync_script = scripts_dir / "sync_to_github.py"

    append_cmd = [
        sys.executable,
        str(append_script),
        "--no-github-sync",
        "--title",
        args.title,
    ]
    if args.date:
        append_cmd.extend(["--date", args.date])
    for value in args.source:
        append_cmd.extend(["--source", value])
    for value in args.issue:
        append_cmd.extend(["--issue", value])
    for value in args.replacement:
        append_cmd.extend(["--replacement", value])
    for value in args.validation:
        append_cmd.extend(["--validation", value])

    message = args.message or f"Update databrick migration skill: {args.title}"
    run(append_cmd)
    run([sys.executable, str(sync_script), "--message", message])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
