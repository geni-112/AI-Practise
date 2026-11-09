#!/usr/bin/env python3
"""Install a complete, verified skill without replacing existing project files."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

from validate_package import SKILL_ROOT, validate

CLIENTS = {'copilot': '.github', 'codex': '.agents', 'claude': '.claude'}


def install(project: Path, client: str) -> Path:
    files = validate()
    project = project.expanduser().resolve()
    dest = project / CLIENTS[client] / 'skills' / SKILL_ROOT.name
    if dest.is_symlink() or any(parent.is_symlink() for parent in dest.parents if parent != project.parent):
        raise ValueError('Refusing to install through a symlink')
    if SKILL_ROOT == dest.resolve() or SKILL_ROOT in dest.resolve().parents or dest.resolve() in SKILL_ROOT.parents:
        raise ValueError('Choose a target project outside the source skill')
    package_files = files + [SKILL_ROOT / 'manifest.json']
    if dest.exists() and any(dest.iterdir()):
        expected = {p.relative_to(SKILL_ROOT).as_posix() for p in package_files}
        actual = {p.relative_to(dest).as_posix() for p in dest.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        if actual == expected and all((dest / p.relative_to(SKILL_ROOT)).read_bytes() == p.read_bytes() for p in package_files):
            print(f'Already installed: {dest}')
            return dest
        raise ValueError(f'Target skill already contains different files: {dest}. Choose another project or explicitly remove the old installation.')
    dest.mkdir(parents=True, exist_ok=True)
    for source in package_files:
        target = dest / source.relative_to(SKILL_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    print(f'Installed {client} skill: {dest}')
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', required=True, choices=CLIENTS)
    parser.add_argument('--project', type=Path, default=Path.cwd(), help='Target project directory (default: current directory)')
    args = parser.parse_args()
    try:
        install(args.project, args.client)
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc))


if __name__ == '__main__':
    main()
