"""Prove HOME refusal without contacting launchd."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(dir='/private/tmp') as folder:
    root = Path(folder)
    home = root / 'home'
    (home / 'Library/LaunchAgents').mkdir(parents=True)
    binary = root / 'bin'
    binary.mkdir()
    calls = root / 'calls'
    fake = binary / 'launchctl'
    fake.write_text(f'#!/bin/sh\necho called >> "{calls}"\n')
    fake.chmod(0o755)
    env = dict(os.environ, HOME=str(home), PATH=str(binary) + ':' + os.environ['PATH'], PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, '-B', str(ROOT / 'install_coordinator.py'), 'install'], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0 and 'Refusing' in result.stderr
    assert not calls.exists()
    assert set(home.rglob('*')) == {home / 'Library', home / 'Library/LaunchAgents'}
    print(f'temp HOME exit: {result.returncode}')
    print(result.stderr.strip())
    print('launchctl invocations: 0; installer writes: 0')
source = subprocess.check_output(['git', 'show', 'origin/main:install_coordinator.py'], cwd=ROOT, text=True, timeout=30)
source = source.replace('from __future__ import annotations', '')
source = 'from __future__ import annotations\n__file__ = ' + repr(str(ROOT / 'install_coordinator.py')) + '\n' + source
before = subprocess.run([sys.executable, '-B', '-c', source, 'status'], capture_output=True, text=True, timeout=30)
after = subprocess.run([sys.executable, '-B', str(ROOT / 'install_coordinator.py'), 'status'], capture_output=True, text=True, timeout=30)
# Ignore the presentation order of directory sets in the JSON report.
import json
assert before.returncode == after.returncode == 0
assert json.loads(before.stdout) == json.loads(after.stdout)
print('real HOME status: exit 0; JSON identical to origin/main')
