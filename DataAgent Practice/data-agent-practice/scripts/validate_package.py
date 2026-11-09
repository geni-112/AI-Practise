#!/usr/bin/env python3
"""Validate the installed Agent Skill using only the Python standard library."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re

SKILL_ROOT = Path(__file__).resolve().parents[1]


def manifest_files(root: Path = SKILL_ROOT) -> list[Path]:
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format') != 1 or not isinstance(manifest.get('files'), dict):
        raise ValueError('Unsupported package manifest')
    files = []
    for name, digest in manifest['files'].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name:
            raise ValueError(f'Unsafe packaged path: {name}')
        if any(part in {'.git', '.openai', '.runtime', 'node_modules', 'dist', '.venv', '__pycache__'} for part in relative.parts):
            raise ValueError(f'Private or generated directory in package: {name}')
        if relative.name.startswith('.env') and relative.name != '.env.example':
            raise ValueError(f'Private environment file in package: {name}')
        path = root.joinpath(*relative.parts)
        if path.is_symlink() or not path.is_file() or root not in path.resolve().parents:
            raise ValueError(f'Missing or unsafe packaged file: {name}')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f'Package hash mismatch: {name}')
        files.append(path)
    return files


def validate(root: Path = SKILL_ROOT) -> list[Path]:
    root = root.resolve()
    files = manifest_files(root)
    skill = (root / 'SKILL.md').read_text(encoding='utf-8')
    if not skill.startswith('---\n') or '\n---\n' not in skill[4:]:
        raise ValueError('SKILL.md needs YAML frontmatter')
    header = skill.split('---\n', 2)[1]
    name = re.search(r'^name: (.+)$', header, re.M)
    description = re.search(r'^description: (.+)$', header, re.M)
    if not name or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name[1]) or len(name[1]) > 64:
        raise ValueError('Invalid Agent Skills name')
    if name[1] != root.name:
        raise ValueError('Skill directory must match frontmatter name')
    if not description or not 1 <= len(description[1]) <= 1024:
        raise ValueError('Description must contain 1-1024 characters')
    for file in files:
        if file.suffix == '.md' and 'assets' not in file.relative_to(root).parts:
            content = file.read_text(encoding='utf-8')
            for target in re.findall(r'\]\(([^)]+)\)', content):
                if '://' not in target and not target.startswith('#'):
                    destination = (file.parent / target.split('#')[0]).resolve()
                    if root not in destination.parents or not destination.is_file():
                        raise ValueError(f'Broken reference in {file.relative_to(root)}: {target}')
    return files


if __name__ == '__main__':
    try:
        files = validate()
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        raise SystemExit(f'Package validation failed: {exc}')
    print(f'Valid data-agent-practice package: {len(files)} files; manifest hashes and references verified.')
