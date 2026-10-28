#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import shlex
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description='Install or undo the local Cursor input gate.')
    parser.add_argument('action', choices=['install', 'status', 'uninstall'])
    parser.add_argument('--bin-dir', type=Path, default=Path.home() / '.local/bin')
    parser.add_argument('--source', type=Path, default=Path(__file__).with_name('cursor_agent_gate.py'))
    args = parser.parse_args()
    folder = args.bin_dir.expanduser().resolve()
    entry = folder / 'cursor-agent'
    backup = folder / 'cursor-agent.before-mac-ops-1'
    receipt = folder / 'cursor-agent.mac-ops-1.json'
    saved = None
    if receipt.is_symlink():
        raise RuntimeError("Install receipt must not be a symlink.")
    if receipt.exists():
        saved = json.loads(receipt.read_text())
        if not isinstance(saved, dict) or saved.get('owner') != 'mac-ops/1.cursor-input-gate.v1':
            raise RuntimeError('Unrecognized install receipt; refusing to overwrite anything.')
        if not all(isinstance(saved.get(key), str) for key in ['original_link', 'real', 'sha256']):
            raise RuntimeError('Invalid install receipt.')
    if args.action == 'status':
        active = receipt.is_file() and backup.is_symlink() and entry.is_file() and not entry.is_symlink()
        if active:
            active = digest(entry) == saved.get('sha256')
        print(json.dumps({'active': active, 'entry': str(entry), 'backup': str(backup)}))
        return
    if args.action == 'uninstall':
        if saved is None:
            raise RuntimeError('No installation receipt.')
        if not backup.is_symlink() or os.readlink(backup) != saved['original_link']:
            raise RuntimeError('Original launcher backup changed; refusing to overwrite anything.')
        if entry.is_symlink() or not entry.is_file() or digest(entry) != saved['sha256']:
            raise RuntimeError('Installed launcher changed; refusing to overwrite anything.')
        os.replace(backup, entry)
        print('Restored original Cursor launcher. The inactive receipt remains at ' + str(receipt))
        return
    if not entry.is_symlink() or os.path.lexists(backup):
        raise RuntimeError('Expected an original Cursor symlink and no existing backup.')
    original = os.readlink(entry)
    if saved and saved['original_link'] != original:
        raise RuntimeError('Existing receipt describes a different original launcher.')
    real = entry.resolve(strict=True)
    if not real.is_file() or not os.access(real, os.X_OK):
        raise RuntimeError('Original Cursor target is not executable.')
    if folder.stat().st_uid != os.getuid() or real == args.source.resolve():
        raise RuntimeError('Launcher folder must belong to this user and the original must be distinct.')
    source = args.source.resolve(strict=True)
    staged = folder / ('cursor-agent.mac-ops-1-stage-' + str(os.getpid()))
    with staged.open('xb') as stream:
        stream.write(source.read_bytes())
    staged.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    saved = {'owner': 'mac-ops/1.cursor-input-gate.v1', 'original_link': original, 'real': str(real), 'sha256': digest(staged)}
    receipt.write_text(json.dumps(saved, indent=2) + '\n')
    receipt.chmod(0o600)
    os.rename(entry, backup)
    try:
        os.replace(staged, entry)
    except BaseException:
        os.replace(backup, entry)
        raise
    print(json.dumps({'installed': str(entry), 'original': original, 'sha256': saved['sha256'],
                      'undo': shlex.join(['mv', str(backup), str(entry)])}))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        sys.exit('cursor gate installer: ' + str(error))
