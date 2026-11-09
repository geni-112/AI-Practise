#!/usr/bin/env python3
"""Install the bundled standard Agent Skill into a project."""
from pathlib import Path
import runpy
import sys

if __name__ == '__main__':
    scripts = Path(__file__).resolve().parent / 'data-agent-practice' / 'scripts'
    sys.path.insert(0, str(scripts))
    runpy.run_path(str(scripts / 'install_skill.py'), run_name='__main__')
