#!/usr/bin/env python3
"""Append a structured migration lesson to references/demo-lessons.md."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path


def bullet_lines(values: list[str]) -> str:
    return "\n".join(f"- {value.strip()}" for value in values if value.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True, help="Demo, session, or lesson title")
    parser.add_argument("--date", default=date.today().isoformat(), help="Entry date, YYYY-MM-DD")
    parser.add_argument("--source", action="append", required=True, help="Observed source pattern")
    parser.add_argument("--issue", action="append", required=True, help="Issue or migration gap")
    parser.add_argument(
        "--replacement",
        action="append",
        required=True,
        help="Verified Huawei replacement or demo-safe approximation",
    )
    parser.add_argument("--validation", action="append", required=True, help="Validation evidence")
    parser.add_argument(
        "--no-github-sync",
        action="store_true",
        help="Append the lesson without syncing the skill mirror to GitHub",
    )
    parser.add_argument(
        "--lessons-file",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "references" / "demo-lessons.md",
        help="Path to demo-lessons.md",
    )
    args = parser.parse_args()

    lessons_file = args.lessons_file.resolve()
    if not lessons_file.exists():
        parser.error(f"lessons file does not exist: {lessons_file}")

    entry = f"""
## {args.date} - {args.title}

Source pattern:
{bullet_lines(args.source)}

Issue:
{bullet_lines(args.issue)}

Huawei replacement:
{bullet_lines(args.replacement)}

Validation:
{bullet_lines(args.validation)}
""".rstrip()

    existing = lessons_file.read_text(encoding="utf-8").rstrip()
    lessons_file.write_text(existing + "\n\n" + entry + "\n", encoding="utf-8")
    print(f"Appended lesson to {lessons_file}")
    if not args.no_github_sync:
        sync_script = Path(__file__).resolve().parent / "sync_to_github.py"
        try:
            subprocess.run(
                [sys.executable, str(sync_script), "--message", f"Update databrick migration skill: {args.title}"],
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"GitHub sync failed; run {sync_script} manually after resolving the issue. Error: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
