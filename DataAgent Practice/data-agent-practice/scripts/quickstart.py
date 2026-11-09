#!/usr/bin/env python3
"""Scaffold and run a local browser demo without model or cloud credentials."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

from scaffold import scaffold


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dest', required=True, type=Path)
    parser.add_argument('--prepare-only', action='store_true', help='Generate files/data without npm installation or a server')
    parser.add_argument('--port', type=int, default=5173)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise SystemExit('Choose a port between 1024 and 65535')
    npm = shutil.which('npm')
    if not args.prepare_only and not npm:
        raise SystemExit('Install Node.js 22.12+ and npm first, or use --prepare-only.')
    try:
        root = scaffold(args.dest, 'browser')
        subprocess.run([sys.executable, 'scripts/package_downloads.py'], cwd=root, check=True)
        if args.prepare_only:
            print('Ready. To start later: npm ci, then npm run dev from the generated project.')
            return
        subprocess.run([npm, 'ci', '--no-audit', '--no-fund'], cwd=root, check=True)
        env = os.environ.copy()
        env['NEXO_BROWSER_ONLY'] = 'true'
        print(f'Open http://127.0.0.1:{args.port} (browser rules; no cloud/model calls). Ctrl+C stops the server.', flush=True)
        subprocess.run([npm, 'run', 'dev', '--', '--host', '127.0.0.1', '--port', str(args.port), '--strictPort'], cwd=root, env=env, check=True)
    except KeyboardInterrupt:
        print('\nDemo stopped. Generated project files are preserved.')
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc))


if __name__ == '__main__':
    main()
