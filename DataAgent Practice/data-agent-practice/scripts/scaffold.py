#!/usr/bin/env python3
"""Create a fresh NEXO project and deterministic synthetic data; no cloud calls."""
from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path
import shutil
import subprocess
import sys

from validate_package import SKILL_ROOT, validate


def scaffold(destination: Path, profile: str = 'browser') -> Path:
    files = validate()
    template = SKILL_ROOT / 'assets' / 'template'
    destination = destination.expanduser()
    if destination.is_symlink():
        raise ValueError('Destination cannot be a symlink')
    destination = destination.resolve()
    if destination == SKILL_ROOT or SKILL_ROOT in destination.parents or destination in SKILL_ROOT.parents:
        raise ValueError('Choose a destination outside the skill package')
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError(f'Destination must be new or empty: {destination}')
    destination.mkdir(parents=True, exist_ok=True)
    for source in files:
        if template in source.parents:
            target = destination / source.relative_to(template)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    environment = (destination / '.env.example').read_text(encoding='utf-8')
    browser = profile == 'browser'
    environment = environment.replace('NEXO_BROWSER_ONLY=true', f'NEXO_BROWSER_ONLY={str(browser).lower()}')
    if browser:
        environment = environment.replace('TEMPORAL_ENABLED=true', 'TEMPORAL_ENABLED=false')
        environment = environment.replace('OPENMETADATA_URL=http://127.0.0.1:8585', 'OPENMETADATA_URL=')
    environment += '\n# New local development key; never commit this file.\nFERNET_KEY=' + base64.urlsafe_b64encode(os.urandom(32)).decode('ascii') + '\n'
    private_env = destination / '.env'
    descriptor = os.open(private_env, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        stream.write(environment)
    subprocess.run([sys.executable, 'scripts/generate_data.py'], cwd=destination, check=True)
    print(f'Created {profile} demo: {destination}')
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dest', required=True, type=Path)
    parser.add_argument('--profile', choices=('browser', 'integrated'), default='browser')
    args = parser.parse_args()
    try:
        scaffold(args.dest, args.profile)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc))


if __name__ == '__main__':
    main()
