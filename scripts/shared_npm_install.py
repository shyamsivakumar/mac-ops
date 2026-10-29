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


def run(*args, cwd=None, capture=False, env=None):
    return subprocess.run(args, cwd=cwd, check=True, text=True, env=env,
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


def detect(root):
    javascript = [manager for manager, files in (
        ('npm', ('package-lock.json', 'npm-shrinkwrap.json')),
        ('pnpm', ('pnpm-lock.yaml',)),
        ('bun', ('bun.lock', 'bun.lockb')),
    ) if any((root / filename).is_file() for filename in files)]
    if len(javascript) > 1:
        raise ValueError('multiple JavaScript lockfiles; choose one package manager')
    python = 'uv' if (root / 'uv.lock').is_file() else 'pip' if (root / 'requirements.txt').is_file() else None
    native = [name for name, filename in (('cocoapods', 'Podfile.lock'), ('swift', 'Package.resolved'))
              if (root / filename).is_file()]
    if javascript and python:
        raise ValueError('JavaScript and Python lockfiles need separate setup directories')
    if (javascript or python) and native:
        raise ValueError('native setup needs its own directory')
    if len(native) > 1:
        raise ValueError('multiple native lockfiles; choose one')
    if javascript:
        return javascript[0]
    if python:
        return python
    if native:
        return native[0]
    raise ValueError('no supported dependency lockfile found')


def git_common(root):
    return Path(run('git', 'rev-parse', '--path-format=absolute', '--git-common-dir', cwd=root, capture=True).strip())


def install_other(root, manager):
    started = time.monotonic()
    if sys.platform != 'darwin':
        raise ValueError('shared setup requires macOS')
    destination = root / ('.venv' if manager in ('uv', 'pip') else 'Pods' if manager == 'cocoapods' else 'node_modules')
    common = git_common(root)
    base = common / 'mac-ops-manager-cache'
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    with locked(base / (hashlib.sha256(str(root).encode()).hexdigest() + '.worktree.lock')):
        if manager != 'swift' and os.path.lexists(destination):
            raise ValueError(f'{destination.name} already exists; refusing to replace it')
        if manager == 'swift' and not (root / 'Package.swift').is_file():
            raise ValueError('Package.swift is required in the requested directory')
        if manager == 'cocoapods' and not any((root / name).is_file() for name in
                                               ('CocoaPods.podfile.yaml', 'CocoaPods.podfile', 'Podfile', 'Podfile.rb')):
            raise ValueError('a CocoaPods manifest is required in the requested directory')
        heavy = str(Path.home() / '.local/bin/heavy')
        if manager == 'swift':
            run(heavy, 'swift', 'package', '--package-path', str(root), 'resolve', cwd=root)
            cache = 'swift-package-cache'
        elif manager == 'cocoapods':
            run(heavy, 'pod', 'install', '--deployment', f'--project-directory={root}', cwd=root)
            cache = 'cocoapods-cache'
        else:
            filename = {'pnpm': 'pnpm-lock.yaml', 'uv': 'uv.lock', 'pip': 'requirements.txt',
                        'bun': 'bun.lock' if (root / 'bun.lock').is_file() else 'bun.lockb'}[manager]
            tool = 'python3' if manager == 'pip' else manager
            version = run(tool, '--version', cwd=root, capture=True).encode()
            digest = hashlib.sha256()
            for data in (manager.encode(), version, os.uname().sysname.encode(), os.uname().release.encode(),
                         os.uname().machine.encode(), (root / filename).read_bytes()):
                digest.update(len(data).to_bytes(8, 'big'))
                digest.update(data)
            cache = base / manager / digest.hexdigest()
            cache.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            if manager == 'pnpm':
                if any((parent / 'pnpm-workspace.yaml').exists() for parent in root.parents):
                    raise ValueError('ancestor pnpm workspaces are not supported')
                env = {key: value for key, value in env.items() if key.lower() != 'npm_config_workspace_dir'}
                workspace = run('pnpm', 'config', 'get', 'workspace-dir', cwd=root, capture=True, env=env).strip()
                if workspace not in ('', 'undefined'):
                    raise ValueError('configured pnpm workspace-dir is not supported')
                command = ('pnpm', 'install', '--frozen-lockfile', '--package-import-method', 'clone',
                           '--modules-dir', 'node_modules', '--virtual-store-dir', 'node_modules/.pnpm',
                           '--lockfile-dir', str(root), '--store-dir', str(cache))
            elif manager == 'bun':
                command = ('bun', 'install', '--frozen-lockfile', '--cache-dir', str(cache), '--backend', 'clonefile')
            elif manager == 'uv':
                env['UV_PROJECT_ENVIRONMENT'] = str(destination)
                env.pop('UV_PROJECT', None)
                command = ('uv', '--project', str(root), 'sync', '--locked', '--no-python-downloads', '--link-mode', 'clone', '--cache-dir', str(cache))
            else:
                run(heavy, 'python3', '-m', 'venv', '.venv', cwd=root)
                command = (str(destination / 'bin/python'), '-m', 'pip', '--isolated', 'install', '--require-hashes', '--cache-dir', str(cache), '-r', 'requirements.txt')
            run(heavy, *command, cwd=root, env=env)
    print(json.dumps({'manager': manager, 'mode': 'installed', 'seconds': round(time.monotonic() - started, 3), 'cache': str(cache)}))


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    manager = detect(root)
    if manager != 'npm':
        install_other(root, manager)
        return
    install_npm(root)


def install_npm(root):
    started = time.monotonic()
    if sys.platform != 'darwin':
        raise ValueError('copy-on-write clone requires macOS')
    common = git_common(root)
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
    print(json.dumps({'manager': 'npm', 'mode': mode, 'seconds': round(time.monotonic() - started, 3), 'key': key}))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'shared worktree setup: {error}', file=sys.stderr)
        sys.exit(1)
