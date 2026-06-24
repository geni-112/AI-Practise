#!/usr/bin/env python3
"""Mirror this skill into the user's GitHub repository."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


DEFAULT_REPO = "https://github.com/geni-112/AI-Practise.git"
DEFAULT_TARGET_DIR = "databrick migration skill"
DEFAULT_CHECKOUT = Path.home() / "Documents" / "Codex" / "skill-github-sync" / "AI-Practise"


def run(command: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def ensure_checkout(repo_url: str, checkout_dir: Path, branch: str) -> None:
    if (checkout_dir / ".git").exists():
        run(["git", "-C", str(checkout_dir), "fetch", "origin", branch])
        run(["git", "-C", str(checkout_dir), "checkout", branch])
        run(["git", "-C", str(checkout_dir), "pull", "--ff-only", "origin", branch])
        return

    checkout_dir.parent.mkdir(parents=True, exist_ok=True)
    if checkout_dir.exists() and any(checkout_dir.iterdir()):
        raise SystemExit(f"checkout directory exists but is not a git repo: {checkout_dir}")
    run(["git", "clone", "--branch", branch, repo_url, str(checkout_dir)])


def copy_skill(skill_dir: Path, checkout_dir: Path, target_dir_name: str) -> Path:
    target_dir = checkout_dir / target_dir_name
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True)

    shutil.copy2(skill_dir / "SKILL.md", target_dir / "SKILL.md")
    for dirname in ["agents", "references", "scripts"]:
        src = skill_dir / dirname
        if src.exists():
            shutil.copytree(
                src,
                target_dir / dirname,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
            )
    return target_dir


def ensure_git_identity(checkout_dir: Path) -> None:
    email = run(["git", "-C", str(checkout_dir), "config", "user.email"], check=False)
    name = run(["git", "-C", str(checkout_dir), "config", "user.name"], check=False)
    if email.returncode != 0 or not email.stdout.strip():
        run(["git", "-C", str(checkout_dir), "config", "user.email", "codex-skill-sync@example.invalid"])
    if name.returncode != 0 or not name.stdout.strip():
        run(["git", "-C", str(checkout_dir), "config", "user.name", "Codex Skill Sync"])


def commit_and_push(checkout_dir: Path, target_dir_name: str, branch: str, message: str) -> bool:
    ensure_git_identity(checkout_dir)
    run(["git", "-C", str(checkout_dir), "add", "--", target_dir_name])
    status = run(["git", "-C", str(checkout_dir), "status", "--porcelain", "--", target_dir_name])
    if not status.stdout.strip():
        print("No GitHub mirror changes to commit.")
        return False

    run(["git", "-C", str(checkout_dir), "commit", "-m", message])
    run(["git", "-C", str(checkout_dir), "push", "origin", branch])
    print(f"Pushed GitHub mirror update to {branch}: {message}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO, help="Git repository URL")
    parser.add_argument("--branch", default="main", help="Target branch")
    parser.add_argument("--checkout-dir", type=Path, default=DEFAULT_CHECKOUT, help="Local checkout directory")
    parser.add_argument("--target-dir", default=DEFAULT_TARGET_DIR, help="Directory inside the repository")
    parser.add_argument("--message", default="Update databrick migration skill", help="Commit message")
    parser.add_argument(
        "--skill-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Local skill directory to mirror",
    )
    args = parser.parse_args()

    skill_dir = args.skill_dir.resolve()
    checkout_dir = args.checkout_dir.resolve()
    if not (skill_dir / "SKILL.md").exists():
        parser.error(f"skill directory missing SKILL.md: {skill_dir}")

    ensure_checkout(args.repo, checkout_dir, args.branch)
    copy_skill(skill_dir, checkout_dir, args.target_dir)
    commit_and_push(checkout_dir, args.target_dir, args.branch, args.message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
