#!/usr/bin/env python3
"""Install the Empryo task system (hub, queue, launchd jobs, config, Herdr mods) from the mac-ops checkout."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
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
MODS = ("cockpit", "coordinator", "ops", "git-graph")


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
    current = json.loads(target.read_text()) if target.exists() else {}
    merged = {**current, **overlay}
    if merged == current:
        return None, target
    return json.dumps(merged, indent=2).encode(), target


def write(target: Path, data: bytes, mode: int, backups: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backups.mkdir(parents=True, exist_ok=True)
        (backups / (str(target).lstrip("/").replace("/", "__"))).write_bytes(
            target.read_bytes()
        )
    tmp = target.with_name(target.name + ".mac-ops-empryo-" + str(os.getpid()))
    tmp.write_bytes(data)
    os.chmod(tmp, mode)
    os.replace(tmp, target)


def changes(checkout: Path, home: Path) -> list[tuple[Path, bytes, int]]:
    wanted = [
        (target, src.read_bytes(), mode) for src, target, mode in plan(checkout, home)
    ]
    wanted += [(target, data, 0o644) for data, target in render_plists(checkout, home)]
    config, config_target = merged_config(checkout, home)
    if config is not None:
        wanted.append((config_target, config, 0o644))
    return [(t, d, m) for t, d, m in wanted if not t.exists() or t.read_bytes() != d]


def install(checkout: Path, dry_run: bool) -> None:
    home = Path.home()
    pending = changes(checkout, home)
    if dry_run:
        print(
            json.dumps(
                {"action": "empryo", "would_write": [str(t) for t, _, _ in pending]},
                indent=2,
            )
        )
        return
    backups = (
        home / ".local/state/mac-ops/empryo-backups" / time.strftime("%Y%m%d-%H%M%S")
    )
    for target, data, mode in pending:
        write(target, data, mode, backups)
    receipt = {
        "checkout": str(checkout),
        "installed_at": time.time(),
        "written": [str(t) for t, _, _ in pending],
    }
    state = home / ".local/state/mac-ops"
    state.mkdir(parents=True, exist_ok=True)
    (state / RECEIPT_NAME).write_text(json.dumps(receipt))
    print(f"Wrote {len(pending)} Empryo files. Backups: {backups}")
    if any(t.parent.name == "LaunchAgents" for t, _, _ in pending) or any(
        t.name == "emp-hub" for t, _, _ in pending
    ):
        print(
            "Launchd jobs and the hub were not restarted. Run `emp drain --restart` to load a new emp-hub; reload changed plists with launchctl bootout and bootstrap."
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
        raise RuntimeError("Empryo install requires macOS")
    install(checkout, args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as exc:
        print("mac-ops: " + str(exc), file=sys.stderr)
        sys.exit(1)
