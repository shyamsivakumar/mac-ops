#!/usr/bin/env python3
"""Install the coordinator (queue, ticket CLI, launchd jobs, config, Herdr mods) from the mac-ops checkout."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import plistlib
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path
from xml.parsers.expat import ExpatError
from xml.sax.saxutils import escape

RECEIPT_NAME = "coordinator-installation.json"
HOME_TOKEN = "@HOME@"
BIN_FILES = (
    "coordq",
    "coordinator-refresh",
    "coordstart",
    "ticket",
)
CONFIG_FILES = ("AGENT-RULES.md", "hooks.json", "agents/code-reviewer.md", "tickets.json")
MODS = ("cockpit", "coordinator", "ops", "git-graph", "worktrees", "ops-panels", "outputs", "shy-tabs")
HERDR_FILES = ("keys.json", "layouts/shyam.json")
# The pi coordinator's own files: guard extension, sandbox profile, settings,
# phone relay note and launchers.
PI_BIN_FILES = ("coord-pi", "coord-ask", "coord-phone")
PI_FILES = (
    ("extensions/coordinator.ts", ".pi/agent-coordinator/extensions/coordinator.ts"),
    ("coordinator.sb", ".pi/agent-coordinator/coordinator.sb"),
    ("settings.json", ".pi/agent-coordinator/settings.json"),
    ("phone-relay/CLAUDE.md", ".pi/agent-coordinator/phone-relay/CLAUDE.md"),
)
TURN_CAP_JOB = "dev.coordinator.turncap"
# A python interpreter running the monitor script and nothing else. A page of
# the script, a grep of it, or a build job that mentions it does not match.
MONITOR_PATTERN = r"[Pp]ython[0-9.]* .*/loop/turn_cap\.py( --[A-Za-z0-9-]+)*$"


def plan(checkout: Path, home: Path) -> list[tuple[Path, Path, int]]:
    root = checkout / "coordinator"
    items = [
        (root / "bin" / name, home / ".local/bin" / name, 0o755) for name in BIN_FILES
    ]
    items += [
        (root / "config" / name, home / ".coordinator" / name, 0o644)
        for name in CONFIG_FILES
    ]
    items += [
        (root / "herdr" / name, home / ".config/herdr-app" / name, 0o644)
        for name in HERDR_FILES
    ]
    pi_root = root / "pi"
    items += [
        (pi_root / "bin" / name, home / ".local/bin" / name, 0o755)
        for name in PI_BIN_FILES
    ]
    items += [
        (pi_root / relative, home / live, 0o644) for relative, live in PI_FILES
    ]
    for mod in MODS:
        base = root / "mods" / mod
        items += [
            (
                f,
                home / ".config/herdr-app/mods" / mod / f.relative_to(base),
                0o755 if os.access(f, os.X_OK) else 0o644,
            )
            for f in sorted(base.rglob("*"))
            if f.is_file()
        ]
    return items


def render_plists(checkout: Path, home: Path) -> list[tuple[bytes, Path]]:
    folder = checkout / "coordinator/launchd"
    # The home path lands in XML text, so it is escaped before substitution.
    replacement = escape(str(home)).encode()
    return [
        (
            src.read_bytes().replace(HOME_TOKEN.encode(), replacement),
            home / "Library/LaunchAgents" / src.name,
        )
        for src in sorted(folder.glob("*.plist"))
    ]


def log_dirs(rendered: list[tuple[bytes, Path]]) -> set[Path]:
    """Return the directories the rendered jobs write their logs into."""
    dirs = set()
    for data, target in rendered:
        try:
            parsed = plistlib.loads(data)
        except (plistlib.InvalidFileException, ExpatError, ValueError) as exc:
            raise RuntimeError(f"Unreadable launchd job {target.name}: {exc}") from exc
        for key in ("StandardOutPath", "StandardErrorPath"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                dirs.add(Path(value).parent)
    return dirs


def ensure_log_dirs(dirs: set[Path], home: Path) -> tuple[list[Path], list[Path]]:
    """Create the log directories this installer owns. launchd does not create
    them, and a job whose log path is missing does not start. Only directories
    under ~/Library/Logs belong to the installer; a job that logs into another
    checkout keeps that directory to itself. Every level below the home
    directory is created on its own and a symlinked level is refused, so the
    tree is never written through a planted link. A refused directory is
    reported and left alone; it must not fail the rest of the install."""
    root = home / "Library/Logs"
    created = []
    refused = []
    for directory in sorted(dirs):
        if not directory.is_relative_to(root) or directory.is_dir():
            continue
        try:
            create_dir_chain(directory, home)
        except ValueError as exc:
            refused.append(directory)
            print(f"Warning: {exc}")
            continue
        created.append(directory)
    return created, refused


def create_dir_chain(directory: Path, home: Path) -> None:
    """Create directory and its missing parents, one level at a time."""
    current = home
    for part in directory.relative_to(home).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Refusing to create a directory through a symlink: {current}")
        if current.exists():
            continue
        current.mkdir()


def monitor_pids(output: str) -> list[int]:
    pids = []
    for line in output.splitlines():
        head = line.split(" ", 1)[0].strip()
        if head.isdigit():
            pids.append(int(head))
    return pids


def run_quiet(argv: list[str]) -> str | None:
    """Run a command and return its output, or None when it cannot run."""
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=15, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout


def parse_launchd_pid(output: str) -> int | None:
    """Read the pid from launchctl output, in the list form or the print
    form."""
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith('"PID"'):
            value = stripped.split("=", 1)[1].strip().rstrip(";").strip('"')
            if value.isdigit():
                return int(value)
        if stripped.startswith("pid ="):
            value = stripped.split("=", 1)[1].strip()
            if value.isdigit():
                return int(value)
    return None


def launchd_pid(label: str) -> int | None:
    """Find the pid of a loaded job. launchctl list works in every domain, so a
    job loaded by the legacy launchctl load is still recognised."""
    listed = run_quiet(["launchctl", "list", label])
    if listed is not None:
        pid = parse_launchd_pid(listed)
        if pid is not None:
            return pid
    printed = run_quiet(["launchctl", "print", f"gui/{os.getuid()}/{label}"])
    return parse_launchd_pid(printed) if printed is not None else None


def manual_pids(pids: list[int], owned: int | None) -> list[int]:
    """Drop the process launchd owns."""
    return [pid for pid in pids if pid != owned]


def manual_monitors(label: str = TURN_CAP_JOB) -> list[int]:
    """Return the turn-cap monitors that launchd does not own. The monitor has
    no lock, so a hand-started copy and the job would double-interrupt
    threads."""
    output = run_quiet(["pgrep", "-fl", MONITOR_PATTERN])
    if output is None:
        return []
    owned = launchd_pid(label)
    return manual_pids(monitor_pids(output), owned)


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
        name = f".mac-ops-coordinator-{uuid.uuid4().hex}"
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
    pending = []
    for target, data, mode in wanted:
        current = read_regular(target)
        if (
            current is None or current[0] != data
            or stat.S_IMODE(current[1].st_mode) != mode
        ):
            pending.append((target, data, mode))
    return pending


def install(checkout: Path, dry_run: bool, home: Path | None = None) -> None:
    home = home or Path.home()
    pending = changes(checkout, home)
    state = home / ".local/state/mac-ops"
    receipt_target = state / RECEIPT_NAME
    # Validate the receipt before any installation writes, even on a no-op.
    read_regular(receipt_target)
    if dry_run:
        print(json.dumps(
            {"action": "coordinator", "would_write": [str(t) for t, _, _ in pending]},
            indent=2,
        ))
        return
    created, _refused = ensure_log_dirs(log_dirs(render_plists(checkout, home)), home)
    for directory in created:
        print(f"Created log directory: {directory}")
    for pid in manual_monitors():
        print(
            f"Warning: a hand-started turn-cap monitor is running (pid {pid}). "
            f"Stop it so only one monitor runs: kill {pid}"
        )
    if not pending:
        print("Wrote 0 coordinator files. Already in sync.")
        return
    transaction = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex
    backups = state / "coordinator-backups" / transaction
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
    print(f"Wrote {len(pending)} coordinator files. Backups: {backups}")
    if any(t.parent.name == "LaunchAgents" for t, _, _ in pending):
        print(
            "Launchd jobs were not restarted. Load the changed jobs with "
            "launchctl bootout and bootstrap, for example: launchctl bootstrap "
            f"gui/$(id -u) ~/{'Library/LaunchAgents'}/{TURN_CAP_JOB}.plist"
        )


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
        raise RuntimeError("Coordinator install requires macOS")
    install(checkout, args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as exc:
        print("mac-ops: " + str(exc), file=sys.stderr)
        sys.exit(1)
