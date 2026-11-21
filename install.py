#!/usr/bin/env python3
"""Install checkout-owned Mac load tools; archive rather than delete on removal."""
import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time

FILES = ("heavy.py", "heavy.sh", "board_governor.py", "board_resources.py", "board_restart.py",
         "board_governor.json", "load_backstop.py", "agent_heavy_wait_pause.py")
HOST_CONFIG = "heavy_hosts.json"
LABELS = ("com.shyam.load-backstop", "com.shyam.board-governor")
OBSOLETE = ("com.shyam.multica-sweep", "com.shyam.multica-failover")


def run(argv, allowed=(0,)):
    result = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=30)
    if result.returncode not in allowed:
        raise RuntimeError(f"{argv[0]} {argv[1]} failed ({result.returncode}): {result.stderr[:180]}")
    return result.stdout


def atomic(path, data, mode=0o600):
    fd, name = tempfile.mkstemp(prefix=".mac-ops-", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(name)


def load_heavy(path):
    spec = importlib.util.spec_from_file_location("mac_ops_install_heavy", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def paths(home, checkout):
    digest = hashlib.sha256()
    for name in FILES:
        digest.update(name.encode() + (checkout / name).read_bytes())
    return {"release": home / ".local/lib/mac-ops" / digest.hexdigest()[:20],
            "state": home / ".local/state/mac-ops", "bin": home / ".local/bin/heavy",
            "agents": home / "Library/LaunchAgents", "legacy": home / ".multica-codex"}


def service_specs(p, host_role="full"):
    specs = {}
    if host_role == "runner":
        return specs
    for label in LABELS:
        script = "load_backstop.py" if label == LABELS[0] else "board_governor.py"
        action = "run" if label == LABELS[0] else "once"
        spec = {"Label": label, "ProgramArguments": ["/usr/bin/python3", "-I", str(p["release"] / script), action],
                "ProcessType": "Background", "RunAtLoad": label == LABELS[0],
                "StandardOutPath": str(p["state"] / (label + ".stdout.log")),
                "StandardErrorPath": str(p["state"] / (label + ".stderr.log")),
                "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"}}
        if label == LABELS[0]:
            spec["KeepAlive"] = True
        else:
            spec["StartInterval"] = 60
            spec["Disabled"] = True
        specs[label] = spec
    return specs


def archive(path, folder):
    if not path.exists() and not path.is_symlink():
        return
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = folder / path.name
    if target.exists() or target.is_symlink():
        target = folder / (path.name + "." + str(time.time_ns()))
    path.rename(target)


def bootout(label):
    domain = f"gui/{os.getuid()}/{label}"
    probe = subprocess.run(["/bin/launchctl", "print", domain], capture_output=True, timeout=10)
    if probe.returncode == 0:
        run(["/bin/launchctl", "bootout", domain])
    deadline = time.monotonic() + 10
    while subprocess.run(["/bin/launchctl", "print", domain], capture_output=True, timeout=10).returncode == 0:
        if time.monotonic() >= deadline:
            raise RuntimeError("launchd service did not stop: " + label)
        time.sleep(0.1)


def migration_guard(p):
    marker = p["state"] / "legacy-registry.json"
    if marker.exists():
        return
    registry = p["legacy"] / "heavy-jobs"
    if registry.exists():
        atomic(marker, json.dumps({"path": str(registry)}).encode())


def legacy_helpers(p):
    helper = p["legacy"] / "heavy.py"
    backup = p["legacy"] / "heavy.mac-ops-cutover-original.py"
    if helper.exists() and not backup.exists():
        shutil.copy2(helper, backup)
    if helper.exists():
        text = "#!/usr/bin/python3\nimport os,sys\n"
        text += "target = " + repr(str(p["release"] / "heavy.py")) + "\n"
        text += "if sys.argv[1:2] in ([\"--watchdog\"],[\"--workload-bootstrap\"]):\n"
        text += "    target = " + repr(str(backup)) + "\n"
        text += "os.execv('/usr/bin/python3', ['/usr/bin/python3','-I',target]+sys.argv[1:])\n"
        atomic(helper, text.encode(), 0o700)
    wrapper = p["legacy"] / "heavy.sh"
    if wrapper.exists():
        text = '#!/bin/sh\nexec /usr/bin/python3 -I ' + shell_quote(str(p["release"] / "heavy.py")) + ' "$@"\n'
        atomic(wrapper, text.encode(), 0o700)


def shell_quote(value):
    return "'" + value.replace("'", "'\"'\"'") + "'"


def prepare_migration(p):
    migration_guard(p)
    for label in OBSOLETE:
        bootout(label)
        archive(p["agents"] / (label + ".plist"), p["agents"] / "_archive")
    bootout(LABELS[0])
    old_state = p["legacy"] / "load-backstop.state.json"
    if old_state.exists() and json.loads(old_state.read_text()).get("paused"):
        raise RuntimeError("legacy backstop still owns paused jobs; resume them before cutover")
    for name in ("board-governor.jsonl", "load-backstop.jsonl"):
        source = p["legacy"] / name
        target = p["state"] / ("legacy-" + name)
        if source.is_file() and not target.exists():
            shutil.copy2(source, target)
    legacy_helpers(p)


def legacy_live(p):
    registry = p["legacy"] / "heavy-jobs"
    if not registry.exists():
        return []
    heavy = load_heavy(p["release"] / "heavy.py")
    table = heavy.process_table()
    found = []
    for record in registry.glob("*/record.json"):
        data = json.loads(record.read_text())
        for key in ("supervisor", "watchdog", "workload"):
            identity = data.get(key)
            if isinstance(identity, dict) and heavy._identity_matches(table.get(identity.get("pid")), identity):
                found.append({"job_id": data.get("job_id"), "kind": key, "pid": identity["pid"], "start": identity["start"]})
    listing = run(["/bin/ps", "-axo", "pid=,command="])
    for line in listing.splitlines():
        fields = line.strip().split(None, 1)
        if len(fields) != 2 or not fields[0].isdigit():
            continue
        pid = int(fields[0])
        command = fields[1]
        if str(p["legacy"] / "heavy") in command and pid in table and not any(x["pid"] == pid for x in found):
            if command.split()[0].endswith(("python3", "python3.9", "Python")):
                found.append({"kind": "legacy-helper", "pid": pid, "start": table[pid].start_token})
    return found


def finalize(p):
    marker = p["state"] / "legacy-registry.json"
    if not marker.exists():
        print("No legacy migration pending")
        return True
    live = legacy_live(p)
    if live:
        print(json.dumps({"migration": "draining", "preserved": live}))
        return False
    old = p["legacy"] / "heavy-jobs"
    new = p["state"] / "heavy-jobs"
    if old.exists():
        archive(old, p["state"] / "history")
    archive(marker, p["state"] / "history")
    print("Legacy heavy jobs drained; new admissions enabled. Historical job state preserved.")
    return True


def require_main_checkout(checkout):
    if not (checkout / ".git").is_dir():
        raise RuntimeError("Install from the main repository checkout, not a worktree or runtime copy")
    branch = run(["git", "-C", checkout, "branch", "--show-current"]).strip()
    if branch != "main":
        raise RuntimeError("Install only from mac-ops main")
    if run(["git", "-C", checkout, "status", "--porcelain", "--untracked-files=no"]).strip():
        raise RuntimeError("Install requires a clean main checkout")
    head = run(["git", "-C", checkout, "rev-parse", "HEAD"]).strip()
    remote = run(["git", "-C", checkout, "rev-parse", "origin/main"]).strip()
    if head != remote:
        raise RuntimeError("Update main to origin/main before installing")
    return head


def install(p, checkout, migrate=False, no_start=False, source_commit=None, host_role="full"):
    if host_role == "runner" and migrate:
        raise RuntimeError("Runner hosts cannot migrate legacy load tools")
    if p["legacy"].exists() and not migrate:
        raise RuntimeError("Legacy load tools exist; use install --migrate to preserve their live jobs")
    local = p["state"].parent.parent
    local.mkdir(mode=0o755, exist_ok=True)
    if local.is_symlink() or local.stat().st_uid != os.getuid() or local.stat().st_mode & 0o022:
        raise RuntimeError("Unsafe local directory")
    state_parent = p["state"].parent
    state_parent.mkdir(mode=0o700, exist_ok=True)
    if state_parent.is_symlink() or state_parent.stat().st_uid != os.getuid() or state_parent.stat().st_mode & 0o077:
        raise RuntimeError("~/.local/state must be a private real directory (mode 0700)")
    for name in ("state", "release"):
        p[name].mkdir(mode=0o700, parents=True, exist_ok=True)
        if p[name].is_symlink() or p[name].stat().st_uid != os.getuid() or p[name].stat().st_mode & 0o077:
            raise RuntimeError("Unsafe private directory: " + str(p[name]))
    for name in FILES:
        atomic(p["release"] / name, (checkout / name).read_bytes(), 0o700 if name.endswith(".sh") else 0o600)
    host_config = p["release"].parent / HOST_CONFIG
    if host_config.is_file():
        atomic(p["release"] / HOST_CONFIG, host_config.read_bytes())
    jobs = p["state"] / "heavy-jobs"
    jobs.mkdir(mode=0o700, exist_ok=True)
    helper = load_heavy(p["release"] / "heavy.py")
    helper.Registry(jobs).ensure_protocol()
    if host_role == "full":
        config = p["state"] / "board-governor.json"
        if not config.exists():
            atomic(config, (checkout / "board_governor.json").read_bytes())
    if migrate:
        prepare_migration(p)
    p["bin"].parent.mkdir(parents=True, exist_ok=True)
    if p["bin"].exists() or p["bin"].is_symlink():
        archive(p["bin"], p["state"] / "install-backups")
    atomic(p["bin"], ('#!/bin/sh\nexec /usr/bin/python3 -I ' + shell_quote(str(p["release"] / "heavy.py")) + ' "$@"\n').encode(), 0o755)
    brew_wrapper = Path("/opt/homebrew/bin/heavy")
    if host_role == "full" and migrate and brew_wrapper.is_symlink() and ".multica-codex" in os.readlink(brew_wrapper):
        archive(brew_wrapper, p["state"] / "install-backups")
        brew_wrapper.symlink_to(p["bin"])
    services = service_specs(p, host_role)
    if services:
        p["agents"].mkdir(parents=True, exist_ok=True)
    for label, spec in services.items():
        if not no_start:
            bootout(label)
        plist = p["agents"] / (label + ".plist")
        archive(plist, p["agents"] / "_archive")
        atomic(plist, plistlib.dumps(spec), 0o644)
    atomic(p["state"] / "installation.json", json.dumps({"checkout": str(checkout), "release": str(p["release"]), "installed_at": time.time(), "source_commit": source_commit, "host_role": host_role}).encode())
    if migrate:
        finalize(p)
    if not no_start and host_role == "full":
        run(["/bin/launchctl", "enable", f"gui/{os.getuid()}/{LABELS[0]}"])
        run(["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}", p["agents"] / (LABELS[0] + ".plist")])
    print("Installed heavy in " + str(p["bin"]))
    print("Add ~/.local/bin to PATH. One controller adjusts heavy and board capacity; the second governor plist stays unloaded to prevent duplicates.")


def archive_legacy(p):
    if (p["state"] / "legacy-registry.json").exists() or legacy_live(p):
        raise RuntimeError("Legacy jobs are still draining")
    for label in LABELS + OBSOLETE:
        plist = p["agents"] / (label + ".plist")
        if plist.exists() and str(p["legacy"]) in plist.read_text():
            raise RuntimeError("Live launchd plist still refers to legacy tools: " + label)
    target = Path.home() / "_archive/multica-codex-20261027"
    if target.exists():
        raise RuntimeError("Archive destination already exists; no overwrite allowed")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    p["legacy"].rename(target)
    print("Moved legacy folder to " + str(target))



def validate_release(p, release_dir):
    release_dir = Path(release_dir).resolve()
    expected_root = Path(p["release"]).resolve().parent
    if release_dir.parent != expected_root or not release_dir.is_dir() or release_dir.is_symlink():
        raise RuntimeError("Rollback release directory is invalid: " + str(release_dir))
    digest = hashlib.sha256()
    for name in FILES:
        candidate = release_dir / name
        if not candidate.is_file() or candidate.is_symlink():
            raise RuntimeError("Rollback release is missing file: " + name)
        digest.update(name.encode() + candidate.read_bytes())
    if digest.hexdigest()[:20] != release_dir.name:
        raise RuntimeError("Rollback release digest does not match directory name: " + release_dir.name)
    return release_dir


def activate_release(p, checkout, release_dir, source_commit, no_start=False):
    release_dir = validate_release(p, release_dir)
    rolled = dict(p, release=release_dir)
    rolled["bin"].parent.mkdir(parents=True, exist_ok=True)
    if rolled["bin"].exists() or rolled["bin"].is_symlink():
        archive(rolled["bin"], rolled["state"] / "install-backups")
    atomic(rolled["bin"], ('#!/bin/sh\nexec /usr/bin/python3 -I ' + shell_quote(str(release_dir / "heavy.py")) + ' "$@"\n').encode(), 0o755)
    if rolled["legacy"].exists():
        legacy_helpers(rolled)
    receipt = rolled["state"] / "installation.json"
    host_role = json.loads(receipt.read_text()).get("host_role", "full") if receipt.is_file() else "full"
    services = service_specs(rolled, host_role)
    if services:
        rolled["agents"].mkdir(parents=True, exist_ok=True)
    for label, spec in services.items():
        if not no_start:
            bootout(label)
        plist = rolled["agents"] / (label + ".plist")
        archive(plist, rolled["agents"] / "_archive")
        atomic(plist, plistlib.dumps(spec), 0o644)
    atomic(rolled["state"] / "installation.json", json.dumps({"checkout": str(checkout), "release": str(release_dir), "installed_at": time.time(), "source_commit": source_commit, "host_role": host_role}).encode())
    if not no_start and host_role == "full":
        run(["/bin/launchctl", "enable", f"gui/{os.getuid()}/{LABELS[0]}"])
        run(["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}", rolled["agents"] / (LABELS[0] + ".plist")])
    print("Rolled back heavy to " + str(release_dir) + " (" + str(source_commit) + ")")


def uninstall(p):
    for label in LABELS:
        bootout(label)
        archive(p["agents"] / (label + ".plist"), p["agents"] / "_archive")
    brew_wrapper = Path("/opt/homebrew/bin/heavy")
    if brew_wrapper.is_symlink() and Path(os.readlink(brew_wrapper)) == p["bin"]:
        archive(brew_wrapper, p["state"] / "uninstall-backups")
    archive(p["bin"], p["state"] / "uninstall-backups")
    print("Uninstalled launchd services and wrapper. Runtime releases, state, logs and running jobs are preserved.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "uninstall", "status", "finalize-migration", "archive-legacy", "rollback"), nargs="?", default="install")
    parser.add_argument("--migrate", action="store_true")
    parser.add_argument("--no-start", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--release", type=Path)
    parser.add_argument("--source-commit")
    parser.add_argument("--host-role", choices=("full", "runner"), default="full")
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parent
    p = paths(Path.home(), checkout)
    receipt = p["state"] / "installation.json"
    if args.action not in ("install", "rollback") and receipt.is_file():
        installed = json.loads(receipt.read_text())
        release = Path(installed["release"])
        if not release.is_absolute() or release.parent != Path.home() / ".local/lib/mac-ops":
            raise RuntimeError("Installed release path is invalid")
        p["release"] = release
    if args.dry_run:
        host_config = p["release"].parent / HOST_CONFIG
        print(json.dumps({"action": args.action, "paths": {k:str(v) for k,v in p.items()}, "host_role": args.host_role, "carry_host_config": str(host_config) if host_config.is_file() else None, "services": service_specs(p, args.host_role), "brew_dependencies": []}, indent=2))
        return
    if sys.platform != "darwin":
        raise RuntimeError("Mac load tools require macOS")
    if args.action == "install":
        source_commit = require_main_checkout(checkout)
        install(p, checkout, args.migrate, args.no_start, source_commit, host_role=args.host_role)
    elif args.action == "rollback":
        if args.release is None or not args.source_commit:
            raise RuntimeError("rollback requires --release and --source-commit")
        activate_release(p, checkout, args.release, args.source_commit, args.no_start)
    elif args.action == "uninstall":
        uninstall(p)
    elif args.action == "archive-legacy":
        archive_legacy(p)
    elif args.action == "finalize-migration":
        if not finalize(p):
            sys.exit(75)
    else:
        receipt = p["state"] / "installation.json"
        print(receipt.read_text() if receipt.exists() else "Not installed")
        print(json.dumps({"legacy_live": legacy_live(p)}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print("mac-ops: " + str(exc), file=sys.stderr)
        sys.exit(1)
