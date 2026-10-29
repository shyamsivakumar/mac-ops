#!/usr/bin/env python3
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager

INSTALLERS = {
    ('esbuild', '0.27.0'): 'sha512-jd0f4NHbD6cALCyGElNpGAOtWxSq46l9X/sWB0Nzd5er4Kz2YTm+Vl0qKFT9KUJvD8+fiO8AvoHhFvEatfVixA==',
    ('fsevents', '2.3.3'): 'sha512-5xoDfX+fL7faATnagmWPpbFtwh/R77WmMMqqHGS65C3vvB0YHrgF+B1YmZ3441tMj5n63k0212XNoJwzlhffQw==',
}


def run(*args, cwd=None, capture=False):
    return subprocess.run(args, cwd=cwd, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


@contextmanager
def locked(path):
    with path.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def inputs(root):
    files = {name: (root / name).read_bytes() if (root / name).exists() else b''
             for name in ('package.json', 'package-lock.json', '.npmrc')}
    config = run('npm', 'config', 'list', '--json', cwd=root, capture=True)
    return {**files, 'config': config.encode(), 'NODE_ENV': os.environ.get('NODE_ENV', '').encode()}


def validate(root, captured):
    if os.environ.get('ESBUILD_BINARY_PATH'):
        raise ValueError('ESBUILD_BINARY_PATH is not relocatable')
    manifest = json.loads(captured['package.json'])
    lock = json.loads(captured['package-lock.json'])
    events = ('preinstall', 'install', 'postinstall', 'prepublish', 'preprepare', 'prepare', 'postprepare')
    if manifest.get('workspaces') or any(k in manifest.get('scripts', {}) for k in events) or (root / 'binding.gyp').exists():
        raise ValueError('workspaces and root install lifecycle scripts are not supported')
    if lock.get('lockfileVersion') not in (2, 3) or not isinstance(lock.get('packages'), dict):
        raise ValueError('npm lockfile version 2 or 3 with packages is required')
    if (root / 'npm-shrinkwrap.json').exists():
        raise ValueError('npm-shrinkwrap.json is not supported')
    for parent in root.parents:
        package = parent / 'package.json'
        if package.exists() and json.loads(package.read_bytes()).get('workspaces'):
            raise ValueError('ancestor npm workspaces are not supported')
    if Path(run('npm', 'prefix', cwd=root, capture=True).strip()).resolve() != root:
        raise ValueError('npm project root differs from requested directory')
    for name, package in lock['packages'].items():
        if package.get('link') or str(package.get('resolved', '')).startswith('file:'):
            raise ValueError(f'local dependency is not supported: {name}')
        resolved = package.get('resolved', '')
        if resolved and not resolved.startswith('https://registry.npmjs.org/'):
            raise ValueError(f'non-registry dependency is not supported: {name}')
        if package.get('hasInstallScript'):
            identity = name.removeprefix('node_modules/')
            expected = f"https://registry.npmjs.org/{identity}/-/{identity}-{package.get('version')}.tgz"
            integrity = INSTALLERS.get((identity, package.get('version')))
            if not integrity or package.get('integrity') != integrity or package.get('resolved') != expected or package.get('name', identity) != identity:
                raise ValueError(f'dependency install script is not supported: {name}')
    config = json.loads(captured['config'])
    if any(config.get(k) for k in ('global', 'dry-run', 'package-lock-only')):
        raise ValueError('global, dry-run and package-lock-only installs are not supported')


def unchanged(root, captured):
    if inputs(root) != captured:
        raise ValueError('dependency inputs changed during setup; cache was not published')
    validate(root, captured)


def main():
    started = time.monotonic()
    root = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    if sys.platform != 'darwin':
        raise ValueError('copy-on-write clone requires macOS')
    common = Path(run('git', 'rev-parse', '--path-format=absolute', '--git-common-dir', cwd=root, capture=True).strip())
    base = common / 'mac-ops-npm-cache'
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination_key = hashlib.sha256(str(root).encode()).hexdigest()
    with locked(base / (destination_key + '.worktree.lock')):
        if os.path.lexists(root / 'node_modules'):
            raise ValueError('node_modules already exists; refusing to replace it')
        captured = inputs(root)
        validate(root, captured)
        digest = hashlib.sha256(b'mac-ops-npm-v2')
        versions = run('node', '-p', 'JSON.stringify([process.version, process.arch, process.platform])', capture=True) + run('npm', '--version', capture=True)
        platform = os.uname()
        for data in [*captured.values(), versions.encode(), platform.sysname.encode(), platform.release.encode(), platform.machine.encode()]:
            digest.update(len(data).to_bytes(8, 'big'))
            digest.update(data)
        key = digest.hexdigest()
        cache = base / key
        with locked(base / (key + '.lock')):
            unchanged(root, captured)
            if cache.is_dir():
                mode = 'cache-hit'
                run('/bin/cp', '-cR', str(cache), str(root / 'node_modules'))
                unchanged(root, captured)
            else:
                mode = 'installed'
                run(str(Path.home() / '.local/bin/heavy'), 'npm', 'ci', '--no-audit', '--no-fund', cwd=root)
                unchanged(root, captured)
                for directory, dirs, files in os.walk(root / 'node_modules'):
                    for name in dirs + files:
                        item = Path(directory) / name
                        if item.is_symlink() and (os.path.isabs(os.readlink(item)) or not item.resolve().is_relative_to(root / 'node_modules')):
                            raise ValueError(f'non-relocatable dependency link: {item}')
                with tempfile.TemporaryDirectory(prefix='npm-cache-', dir=base) as stage:
                    clone = Path(stage) / 'node_modules'
                    run('/bin/cp', '-cR', str(root / 'node_modules'), str(clone))
                    clone.rename(cache)
    print(json.dumps({'mode': mode, 'seconds': round(time.monotonic() - started, 3), 'key': key}))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'shared npm setup: {error}', file=sys.stderr)
        sys.exit(1)
