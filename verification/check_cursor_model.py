#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    source = Path(__file__).resolve().parent / 'cursor_input'
    jar = Path(os.environ.get('MAC_OPS_TLA_JAR', str(Path.home() / 'Code/llmwiki/runtime/tla/tla2tools.jar')))
    java = Path(os.environ.get('MAC_OPS_JAVA_BIN', '/opt/homebrew/opt/openjdk@17/bin/java'))
    if not jar.is_file() or not java.is_file() or not os.access(java, os.X_OK):
        raise RuntimeError('Set MAC_OPS_TLA_JAR and MAC_OPS_JAVA_BIN to existing TLC and Java installations.')
    temp_root = Path(os.environ['TMPDIR']).resolve(strict=True)
    scratch = Path(tempfile.mkdtemp(prefix='cursor-model-', dir=temp_root))
    names = ['CursorInputGate.tla', 'CursorInputGate.cfg', 'BeforeWrite.cfg']
    for name in names:
        shutil.copyfile(source / name, scratch / name)
    receipt = {'jar_sha256': hashlib.sha256(jar.read_bytes()).hexdigest(),
               'java': str(java), 'sources': {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in names}}
    for config, expected in [('CursorInputGate.cfg', 0), ('BeforeWrite.cfg', 12)]:
        command = [str(java), '-Xmx128m', '-Djava.io.tmpdir=' + str(scratch), '-cp', str(jar),
                   'tlc2.TLC', '-workers', '1', '-metadir', str(scratch / ('states-' + config)),
                   '-config', config, 'CursorInputGate.tla']
        result = subprocess.run(command, cwd=scratch, capture_output=True, text=True, timeout=45)
        log = scratch / (config + '.log')
        log.write_text(result.stdout + result.stderr)
        receipt[config] = {'exit': result.returncode, 'log': str(log)}
        if result.returncode != expected:
            raise RuntimeError(f'{config} exited {result.returncode}, expected {expected}. Read {log}')
        if expected == 12 and 'Invariant ReleaseAfterAcknowledgement is violated' not in (result.stdout + result.stderr):
            raise RuntimeError('The unsafe variant failed for an unexpected reason. Read ' + str(log))
    (scratch / 'receipt.json').write_text(json.dumps(receipt, indent=2))
    print('PASS: ordering model; unsafe early-release variant rejected. Receipt: ' + str(scratch / 'receipt.json'))


if __name__ == '__main__':
    try:
        main()
    except (OSError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        sys.exit('Cursor model verification failed: ' + str(error))
