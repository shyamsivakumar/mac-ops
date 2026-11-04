#!/usr/bin/env python3
"""Install the Empryo task system (hub, queue, launchd jobs, config, Herdr mods) from the mac-ops checkout."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import stat
import sys
import time
import uuid
from pathlib import Path

RECEIPT_NAME = "empryo-installation.json"
HOME_TOKEN = "@HOME@"
BIN_FILES = (
    "emp-hub",
    "emp",
    "empq",
    "emp-health",
    "coordinator-refresh",
    "coordstart",
)
CONFIG_FILES = ("EMPRYO.md", "hooks.json", "agents/code-reviewer.md")
MODS = ("cockpit", "coordinator", "ops", "git-graph", "worktrees")


def plan(checkout: Path, home: Path) -> list[tuple[Path, Path, int]]:
    root = checkout / "empryo"
    items = [
        (root / "bin" / name, home / ".local/bin" / name, 0o755) for name in BIN_FILES
    ]
    items += [(root / "hub/routing.json", home / ".empryo-hub/routing.json", 0o644)]
    items += [
        (root / "config" / name, home / ".empryo" / name, 0o644)
        for name in CONFIG_FILES
    ]
    for mod in MODS:
        base = root / "mods" / mod
        items += [
            (f, home / ".config/herdr-app/mods" / mod / f.relative_to(base), 0o644)
            for f in sorted(base.rglob("*"))
            if f.is_file()
        ]
    return items


def render_plists(checkout: Path, home: Path) -> list[tuple[bytes, Path]]:
    folder = checkout / "empryo/launchd"
    return [
        (
            src.read_bytes().replace(HOME_TOKEN.encode(), str(home).encode()),
            home / "Library/LaunchAgents" / src.name,
        )
        for src in sorted(folder.glob("*.plist"))
    ]


def merged_config(checkout: Path, home: Path) -> tuple[bytes | None, Path]:
    target = home / ".empryo/config.json"
    overlay = json.loads((checkout / "empryo/config/routing-config.json").read_text())
    data = read_regular(target)
    current = json.loads(data[0]) if data is not None else {}
    if not isinstance(current, dict):
        raise ValueError(f"Config must be an object: {target}")

    def merge(current, overlay):
        result = dict(current)
        for key, value in overlay.items():
            previous = result.get(key)
            if isinstance(value, dict):
                result[key] = merge(previous if isinstance(previous, dict) else {}, value)
            else:
                result[key] = value
        return result

    merged = merge(current, overlay)
    if merged == current:
        return None, target
    return json.dumps(merged, indent=2).encode(), target


@contextlib.contextmanager
def safe_parent(target: Path, *, create: bool = False):
    """Pin every directory without following symlinks, including during replacement."""
    target = target.absolute()
    if ".." in target.parts:
        raise ValueError(f"Unsafe path: {target}")
    fd = os.open(target.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in target.parts[1:-1]:
            if create:
                try:
                    os.mkdir(part, 0o755, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = child
        try:
            info = os.stat(target.name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISREG(info.st_mode):
                raise ValueError(f"Not a regular file: {target}")
        yield fd
    finally:
        os.close(fd)


def read_regular(target: Path):
    try:
        with safe_parent(target) as parent:
            fd = os.open(
                target.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
            )
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError(f"Not a regular file: {target}")
                return stream.read(), info
    except FileNotFoundError:
        return None


def atomic_write(target: Path, data: bytes, mode: int) -> None:
    with safe_parent(target, create=True) as parent:
        name = f".mac-ops-empryo-{uuid.uuid4().hex}"
        fd = os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=parent,
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fchmod(stream.fileno(), mode)
                os.fsync(stream.fileno())
            os.replace(name, target.name, src_dir_fd=parent, dst_dir_fd=parent)
        finally:
            try:
                os.unlink(name, dir_fd=parent)
            except FileNotFoundError:
                pass


def write(target: Path, data: bytes, mode: int, backups: Path) -> None:
    manifest_path = backups / "manifest.json"
    saved = read_regular(manifest_path)
    manifest = json.loads(saved[0]) if saved is not None else {"version": 1, "files": []}
    if not any(entry["path"] == str(target) for entry in manifest["files"]):
        original = read_regular(target)
        entry = {"path": str(target), "backup": None}
        if original is not None:
            contents, info = original
            name = f"file-{len(manifest['files']):04d}"
            atomic_write(backups / name, contents, stat.S_IMODE(info.st_mode))
            entry.update(
                backup=name, mode=stat.S_IMODE(info.st_mode),
                atime_ns=info.st_atime_ns, mtime_ns=info.st_mtime_ns,
            )
        manifest["files"].append(entry)
        atomic_write(manifest_path, json.dumps(manifest, indent=2).encode(), 0o600)
    atomic_write(target, data, mode)


def changes(checkout: Path, home: Path) -> list[tuple[Path, bytes, int]]:
    wanted = [
        (target, src.read_bytes(), mode) for src, target, mode in plan(checkout, home)
    ]
    wanted += [(target, data, 0o644) for data, target in render_plists(checkout, home)]
    config, config_target = merged_config(checkout, home)
    if config is not None:
        wanted.append((config_target, config, 0o644))
    pending = []
    for target, data, mode in wanted:
        current = read_regular(target)
        if (
            current is None or current[0] != data
            or stat.S_IMODE(current[1].st_mode) != mode
        ):
            pending.append((target, data, mode))
    return pending


def install(checkout: Path, dry_run: bool) -> None:
    home = Path.home()
    pending = changes(checkout, home)
    state = home / ".local/state/mac-ops"
    receipt_target = state / RECEIPT_NAME
    # Validate the receipt before any installation writes, even on a no-op.
    read_regular(receipt_target)
    if dry_run:
        print(json.dumps(
            {"action": "empryo", "would_write": [str(t) for t, _, _ in pending]},
            indent=2,
        ))
        return
    if not pending:
        print("Wrote 0 Empryo files. Already in sync.")
        return
    transaction = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex
    backups = state / "empryo-backups" / transaction
    # Reserve a unique transaction using the same no-follow directory walk.
    with safe_parent(backups / "manifest.json", create=True):
        pass
    print(f"Backup transaction: {backups}", flush=True)
    for target, data, mode in pending:
        write(target, data, mode, backups)
    receipt = {
        "checkout": str(checkout),
        "installed_at": time.time(),
        "written": [str(t) for t, _, _ in pending],
        "backups": str(backups),
    }
    write(receipt_target, json.dumps(receipt).encode(), 0o600, backups)
    print(f"Wrote {len(pending)} Empryo files. Backups: {backups}")
    if any(t.parent.name == "LaunchAgents" for t, _, _ in pending) or any(
        t.name == "emp-hub" for t, _, _ in pending
    ):
        print("Launchd jobs and the hub were not restarted. Run `emp drain --restart` to load a new emp-hub; reload changed plists with launchctl bootout and bootstrap.")


def status(checkout: Path) -> None:
    pending = changes(checkout, Path.home())
    print(
        json.dumps(
            {"in_sync": not pending, "differs": [str(t) for t, _, _ in pending]},
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("install", "status"), nargs="?", default="install"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parent
    if args.action == "status":
        status(checkout)
        return
    if not args.dry_run and sys.platform != "darwin":
        raise RuntimeError("Empryo install requires macOS")
    install(checkout, args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as exc:
        print("mac-ops: " + str(exc), file=sys.stderr)
        sys.exit(1)
