#!/usr/bin/env python3
"""Install the coordinator (queue, ticket CLI, launchd jobs, config, Herdr mods) from the mac-ops checkout."""

from __future__ import annotations

import argparse
import contextlib
import fnmatch
import hashlib
import json
import os
import plistlib
import pwd
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path
from unittest import mock
from xml.parsers.expat import ExpatError
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent / "coordinator/bin"))
import models

RECEIPT_NAME = "coordinator-installation.json"
HOME_TOKEN = "@HOME@"
CONFIG_FILES = ("AGENT-RULES.md", "hooks.json", "agents/code-reviewer.md", "tickets.json", "factory.json")
# The board config belongs to the machine. The policy the coordinator runs
# with is decided on the Mac, so the installed copy is the live file and the
# repository copy is only the seed for a machine that has none. A local
# policy edit is not installed drift, the status check does not report it
# and an install never writes over it.
LOCAL_CONFIG_FILES = ("tickets.json",)
MODS_DIR = ".config/herdr-app/mods"
MODS = ("cockpit", "coordinator", "ops", "git-graph", "worktrees", "ops-panels", "outputs", "shy-tabs", "kpane")
HERDR_FILES = ("keys.json", "layouts/shyam.json")
WORKTREE_SCAN_DIR = "scripts/worktree-cleaner"
TASK_ROUTER = ".pi/agent/extensions/task-router.ts"
ROUTE_LEVELS = {
    "quick": "low",
    "chore": "medium",
    "standard": "medium",
    "ui": "medium",
    "research": "medium",
    "rca": "high",
    "risky": "high",
    "design": "high",
    "hard": "xhigh",
}
ROUTES_COMMENT = (
    "// Generated from coordinator/models.json in mac-ops by install_coordinator.py."
    " Do not edit by hand.\n"
)
ROUTES_END = "// End generated\n"
ROUTES_BLOCK = re.compile(
    r"(?:// Generated from[^\n]*\n)?const ROUTES: Record<string, string\[\]> = \{.*?\n\};\n"
    r"(?:const SHARED_IDENTITIES.*?// End generated\n)?",
    re.DOTALL,
)
SHARED_BLOCKS = """const SHARED_BLOCKS_PATH = join(process.env.COORDQ_DIR ?? join(homedir(), "Code", "coordinator", "queue"), "providers-blocked.json");

function sharedBlocked(): Set<string> {
	if (!existsSync(SHARED_BLOCKS_PATH)) return new Set();
	const blocked = JSON.parse(readFileSync(SHARED_BLOCKS_PATH, "utf8")).blocked;
	if (typeof blocked !== "object" || blocked === null || Array.isArray(blocked)) throw new Error(`${SHARED_BLOCKS_PATH} must hold a blocked object`);
	return new Set(Object.entries(blocked).filter(([, e]: [string, any]) => !(Number.isFinite(e?.expires_at) && e.expires_at <= Date.now() / 1000)).map(([key]) => key));
}
"""
SHARED_CHECK = (
    '\tif (sharedBlocked().has(SHARED_IDENTITIES[entry.key] ?? "")) return "blocked in the shared provider store";\n'
)
BLOCK_ANCHOR = "\tconst block = blocks[entry.key];\n"
OWNERSHIP_PARAGRAPH = re.compile(r" \* Ownership:.*?\n \*\n", re.DOTALL)
OWNERSHIP_TEXT = (
    " * Ownership: mac-ops install_coordinator.py regenerates the ROUTES table on every\n"
    " * install from coordinator/models.json in the mac-ops checkout. Change the model\n"
    " * list there and reinstall; this file is overwritten.\n"
    " *\n"
)
POLICY_PARAGRAPH = re.compile(r" \* Routing policy.*?\n(?= \* Reviews are not routed)", re.DOTALL)
POLICY_TEXT = (
    " * Routing policy: every route tries the pi models of the build list in\n"
    " * coordinator/models.json, in that order, and skips any the shared provider\n"
    " * store (providers-blocked.json in the queue folder) has blocked.\n"
)
ARCHIVE_DIR = ".coordinator/archive/2026-11-18-model-lists"
ARCHIVED_LISTS_FILE = "tickets.json.models-and-types.json"
OLD_LIST_SECTIONS = ("models", "types")
OLD_LIST_FILES = (
    (".coordinator", "tickets.json.bak-*"),
    (".pi/agent/extensions", "task-router-blocks.json*"),
)
ARCHIVE_README = (
    "# Model lists replaced by models.json (2026-11-18)\n\n"
    "`~/.coordinator/models.json` is the only place models are listed. "
    "These files held the lists it replaced:\n\n"
    f"- `{ARCHIVED_LISTS_FILE}`: the `models` and `types` sections of `tickets.json`.\n"
    "- `tickets.json.bak-*`: earlier backups of `tickets.json`.\n"
    "- `task-router-blocks.json*`: the pi route block list from the extensions folder.\n\n"
    "To roll back, reinstall the earlier mac-ops release, put the `models` and `types` "
    "sections back into `~/.coordinator/tickets.json`, and move the other files back "
    "to where they were.\n"
)
# The pi coordinator's own files: guard extension, sandbox profile, settings,
# phone relay note and launchers.
PI_BIN_FILES = ("coord-pi", "coord-ask", "coord-phone", "coord-tick", "kpane", "kshow")
PI_FILES = (
    ("extensions/coordinator.ts", ".pi/agent-coordinator/extensions/coordinator.ts"),
    ("coordinator.sb", ".pi/agent-coordinator/coordinator.sb"),
    ("settings.json", ".pi/agent-coordinator/settings.json"),
    ("antigravity-acp-provider/config.json", ".pi/agent-coordinator/antigravity-acp-provider/config.json"),
    ("subagent-manager/settings.json", ".pi/agent-coordinator/subagent-manager/settings.json"),
    ("subagent-manager/agents/architect.yml", ".pi/agent-coordinator/subagent-manager/agents/architect.yml"),
    ("subagent-manager/agents/coder.yml", ".pi/agent-coordinator/subagent-manager/agents/coder.yml"),
    ("subagent-manager/agents/researcher.yml", ".pi/agent-coordinator/subagent-manager/agents/researcher.yml"),
    ("subagent-manager/agents/reviewer.yml", ".pi/agent-coordinator/subagent-manager/agents/reviewer.yml"),
    ("subagent-manager/agents/tasker.yml", ".pi/agent-coordinator/subagent-manager/agents/tasker.yml"),
    ("subagent-manager/agents/writer.yml", ".pi/agent-coordinator/subagent-manager/agents/writer.yml"),
    ("phone-relay/CLAUDE.md", ".pi/agent-coordinator/phone-relay/CLAUDE.md"),
)
TURN_CAP_JOB = "dev.coordinator.turncap"
# The jobs the coordinator retired. A retired job has no plist in the
# repository, so the installer must also take the installed copy away and
# unload the running job: otherwise the job stays loaded and keeps
# running. dev.coordinator.overnight ran the same `overnight shift` as
# dev.coordinator.lanes; the lanes job is kept because the lane watchdog and
# the tick check its label and lanes.log.
RETIRED_JOBS: tuple[str, ...] = ("dev.coordinator.overnight",)
RETIRED_FILES = (("loop", "turn_cap.py"), ("loop", "board.py"))
# The overnight runner's on-disk contract. The folders come from the
# overnight runner spec (section 6, revision 2). The shift keeps no second
# queue here: the board is the list.
OVERNIGHT_DIRS = ("run", "receipts", "inbox", "staging")
OVERNIGHT_README = ("overnight", "README.md")
HILLCLIMB_SOURCE = "coordinator/evals/hillclimb"
LOOP_SOURCE = "coordinator/loop"
LOOP_FILES = ("stuck.py", "watch.py")
HILLCLIMB_FILES = ("build_labels.py", "daily3.py", "burst.py", "arms/plain_agent.py", "README.md")
OVERNIGHT_BIN_FILES = ("overnight",) + tuple(
    path.name for path in sorted(
        (Path(__file__).resolve().parent / "coordinator/overnight").glob("*.py")
    ) if path.is_file()
)
DRIFT_CODE_SUFFIXES = (".py", ".sh", ".mjs", ".ts")
DRIFT_SKIP_DIRS = frozenset(
    ("archive", "backups", "evidence", "inbox", "notes", "thoughts", "migration", "__pycache__")
)
LOCAL_ONLY_CODE = ("set-posthog*.sh",)
GITIGNORE_ENTRY = ".overnight/"
GITIGNORE_BLOCK = (
    "# Overnight runner scratch, installed by mac-ops\n"
    "# The overnight shift's folders hold receipts and logs, never code.\n"
    ".overnight/\n"
)
# A python interpreter running the monitor script and nothing else. A page of
# the script, a grep of it, or a build job that mentions it does not match.
MONITOR_PATTERN = r"[Pp]ython[0-9.]* .*/\.local/bin/turn_cap\.py( --[A-Za-z0-9-]+)*$"


def plan(checkout: Path, home: Path) -> list[tuple[Path, Path, int]]:
    root = checkout / "coordinator"
    items = [
        (source, home / ".local/bin" / source.relative_to(root / "bin"),
         0o755 if os.access(source, os.X_OK) else 0o644)
        for source in sorted((root / "bin").rglob("*"))
        if source.is_file() and "__pycache__" not in source.parts
        and source.suffix != ".pyc"
    ]
    items += [
        (root / "config" / name, home / ".coordinator" / name, 0o644)
        for name in CONFIG_FILES
        if name not in LOCAL_CONFIG_FILES
        or not (home / ".coordinator" / name).exists()
    ]
    items.append((root / "models.json", home / ".coordinator/models.json", 0o644))
    items += [
        (root / "rules/answers.js", home / target, 0o644)
        for target in (".coordinator/answers.js", f"{MODS_DIR}/coordinator/answers.js")
    ]
    items += [
        (root / "overnight" / name, home / ".local/bin" / name, 0o755)
        for name in OVERNIGHT_BIN_FILES
    ]
    items += [
        (root / "herdr" / name, home / ".config/herdr-app" / name, 0o644)
        for name in HERDR_FILES
    ]
    items.append((checkout / WORKTREE_SCAN_DIR / "scan.sh", home / ".local/bin/worktree-scan", 0o755))
    items.append((checkout / WORKTREE_SCAN_DIR / "scan-forwarder.sh", home / MODS_DIR / "worktrees/scan.sh", 0o755))
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
                home / MODS_DIR / mod / f.relative_to(base),
                0o755 if os.access(f, os.X_OK) else 0o644,
            )
            for f in sorted(base.rglob("*"))
            if f.is_file()
        ]
    return items


def shim_item(checkout: Path, home: Path, path: str) -> tuple[Path, bytes, int] | None:
    """Return the observation shim for ~/.local/bin/gh, or None when it would
    not run first. The real gh is resolved once, here, from PATH without the
    shim's own folder, and baked into the installed file."""
    target = home / ".local/bin/gh"
    folders = path.split(os.pathsep)
    real = shutil.which("gh", path=os.pathsep.join(f for f in folders if f != str(target.parent)))
    if real is None:
        return None
    if Path(real).resolve() == target.resolve():
        raise RuntimeError(f"{real} is the shim itself; refusing to install it")
    if str(target.parent) not in folders or folders.index(str(target.parent)) > folders.index(str(Path(real).parent)):
        return None
    source = (checkout / "coordinator/shim/gh").read_text().replace("@REAL_GH@", real)
    return target, source.encode(), 0o755


def task_router_text(text: str, routes: dict[str, list[str]], identities: dict[str, str]) -> str:
    """Return the task-router.ts text with its ROUTES table rebuilt from routes.

    Each route tries the models routes lists for it in order, at the route's thinking
    level. identities names each route's entry in the shared provider store, and
    the router skips an entry that store has blocked each time it picks one. The
    header paragraphs that told a reader to edit the table by hand are replaced."""
    lines = "".join(
        f"\t{route}: [{', '.join(json.dumps(f'{model}:{level}') for model in routes[route])}],\n"
        for route, level in ROUTE_LEVELS.items()
    )
    shared = "".join(f"\t{json.dumps(spec)}: {json.dumps(identity)},\n" for spec, identity in identities.items())
    block = (f"{ROUTES_COMMENT}const ROUTES: Record<string, string[]> = {{\n{lines}}};\n"
             f"const SHARED_IDENTITIES: Record<string, string> = {{\n{shared}}};\n{SHARED_BLOCKS}{ROUTES_END}")
    for pattern, replacement in (
        (ROUTES_BLOCK, block),
        (OWNERSHIP_PARAGRAPH, OWNERSHIP_TEXT),
        (POLICY_PARAGRAPH, POLICY_TEXT),
    ):
        text, count = pattern.subn(lambda _match, new=replacement: new, text, count=1)
        if not count:
            raise RuntimeError(f"task-router.ts has no section matching {pattern.pattern[:40]}")
    if SHARED_CHECK not in text:
        if text.count(BLOCK_ANCHOR) != 1:
            raise RuntimeError("task-router.ts has no single place to check the shared provider store")
        text = text.replace(BLOCK_ANCHOR, SHARED_CHECK + BLOCK_ANCHOR)
    return text


def without_old_lists(data: bytes) -> bytes | None:
    """Return tickets.json without its model lists, or None when it has none."""
    config = json.loads(data)
    if not any(section in config for section in OLD_LIST_SECTIONS):
        return None
    kept = {k: v for k, v in config.items() if k not in OLD_LIST_SECTIONS}
    return (json.dumps(kept, indent=2) + "\n").encode()


def old_list_files(home: Path) -> list[Path]:
    return sorted(
        path for folder, pattern in OLD_LIST_FILES for path in (home / folder).glob(pattern)
    )


def archive_model_lists(home: Path) -> list[Path]:
    """Copy the old lists into the archive and move the old list files there.

    Nothing is deleted. The copy of the `models` and `types` sections is taken
    from the live tickets.json before the install strips them, so it runs
    before the files are written."""
    archive = home / ARCHIVE_DIR
    live = read_regular(home / ".coordinator/tickets.json")
    config = json.loads(live[0]) if live is not None else {}
    sections = {k: config[k] for k in OLD_LIST_SECTIONS if k in config}
    moved = []
    if sections:
        copy = (json.dumps(sections, indent=2) + "\n").encode()
        target = archive / ARCHIVED_LISTS_FILE
        existing = read_regular(target)
        if existing is not None and existing[0] != copy:
            target = archive / f"tickets.json.models-and-types.{digest(copy)[:16]}.json"
            existing = read_regular(target)
        if existing is None:
            atomic_write(target, copy, 0o644)
            moved.append(target)
    for path in old_list_files(home):
        archive.mkdir(parents=True, exist_ok=True)
        target = archive / path.name
        if target.exists():
            stem = f"{path.name}.{digest(path.read_bytes())[:16]}"
            target = archive / stem
            count = 1
            while target.exists():
                count += 1
                target = archive / f"{stem}.{count}"
        path.rename(target)
        moved.append(target)
    if moved:
        atomic_write(archive / "README.md", ARCHIVE_README.encode(), 0o644)
    return moved


def checkout_pi_models(checkout: Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    with mock.patch.dict(os.environ, {"COORDINATOR_MODELS": str(checkout / "coordinator/models.json")}):
        return {route: models.pi_routes(route) for route in ROUTE_LEVELS}, models.pi_identities()


def coordinator_dir(home: Path, override: str | None = None) -> Path:
    """Return the coordinator runtime folder that holds the overnight layout.

    The default is the runtime folder the coordinator already uses. An
    override lets a caller point the installer at another checkout."""
    if override:
        return Path(override).expanduser()
    from_env = os.environ.get("MAC_OPS_COORDINATOR_DIR")
    if from_env:
        return Path(from_env).expanduser()
    return home / "Code" / "coordinator"


def overnight_root(coordinator: Path) -> Path:
    return coordinator / ".overnight"


def overnight_dirs(coordinator: Path) -> list[Path]:
    root = overnight_root(coordinator)
    return [root / name for name in OVERNIGHT_DIRS]


def git_toplevel(path: Path) -> Path | None:
    """Return the repository that contains path, or None when there is none."""
    output = run_quiet(["git", "-C", str(path), "rev-parse", "--show-toplevel"])
    if output is None:
        return None
    top = output.strip()
    return Path(top) if top else None


def git_ignored(coordinator: Path) -> bool:
    """Return True when git already ignores the overnight folder."""
    result = run_status(["git", "-C", str(coordinator), "check-ignore", "-q",
                         str(overnight_root(coordinator))])
    return result == 0


def gitignore_item(coordinator: Path) -> tuple[Path, bytes] | None:
    """Return the ignore file to write and its new bytes, or None when the
    overnight folder is already ignored or no repository contains it."""
    top = git_toplevel(coordinator)
    if top is None:
        return None
    if git_ignored(coordinator):
        return None
    ignore = top / ".gitignore"
    try:
        current = read_regular(ignore)
    except OSError as exc:
        # A symlinked ignore file, or one that cannot be read, is left alone.
        print(f"Warning: leaving {ignore} alone: {exc}")
        return None
    text = current[0].decode("utf-8", "replace") if current else ""
    if any(line.strip() == GITIGNORE_ENTRY for line in text.splitlines()):
        return None
    body = text.rstrip("\n")
    updated = (body + "\n\n" + GITIGNORE_BLOCK) if body else GITIGNORE_BLOCK
    return ignore, updated.encode()


def render_plists(checkout: Path, home: Path) -> list[tuple[bytes, Path]]:
    folder = checkout / "coordinator/launchd"
    # The home path lands in XML text, so it is escaped before substitution.
    replacement = escape(str(home)).encode()
    return [
        (
            src.read_bytes().replace(HOME_TOKEN.encode(), replacement),
            home / "Library/LaunchAgents" / src.name,
        )
        for src in sorted([*folder.glob("*.plist"), checkout / WORKTREE_SCAN_DIR / "com.shyam.worktree-scan.plist"])
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


def require_real_home() -> None:
    actual = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    configured = os.environ.get("HOME")
    home = Path(configured).resolve() if configured else None
    temporary = home is not None and any(
        home.is_relative_to(root) for root in (Path("/tmp").resolve(), Path("/private/tmp"))
    )
    if home != actual or temporary:
        raise RuntimeError("Refusing coordinator install or launchctl: HOME must be the real user home and outside /tmp")


def run_quiet(argv: list[str]) -> str | None:
    """Run a command and return its output, or None when it cannot run."""
    if argv and Path(argv[0]).name == "launchctl":
        require_real_home()
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=15, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout


def run_status(argv: list[str], *, capture_error: list[str] | None = None) -> int | None:
    """Run a command and return its exit code, or None when it cannot run.

    When capture_error is given, the text the command refused with is
    appended to it, so a refusal can be reported as it was written."""
    if argv and Path(argv[0]).name == "launchctl":
        require_real_home()
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=15, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if capture_error is not None:
        capture_error.append((result.stderr or result.stdout or "").strip())
    return result.returncode


def run_status_text(argv: list[str]) -> tuple[int | None, str]:
    """Run a command and return its exit code and the text it refused with."""
    errors: list[str] = []
    code = run_status(argv, capture_error=errors)
    return code, (errors[0] if errors else "")


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


def retired_plist(label: str, home: Path) -> Path:
    """Return the installed path of a retired job's plist."""
    return home / "Library" / "LaunchAgents" / f"{label}.plist"


def retired_plists(home: Path) -> list[Path]:
    """Return the installed plists of the retired jobs that are still there.

    One helper builds the list, so the dry run, the status and the
    retirement itself all name the same paths the same way."""
    paths = [retired_plist(label, home) for label in RETIRED_JOBS]
    return [path for path in paths if path.is_file()]


def retired_files(coordinator: Path) -> list[Path]:
    paths = [coordinator.joinpath(*parts) for parts in RETIRED_FILES]
    return [path for path in paths if path.is_file()]


def job_loaded(label: str) -> bool:
    """Return True when launchd has the job loaded."""
    return run_status(["launchctl", "list", label]) == 0


def retire_jobs(home: Path) -> list[str]:
    """Unload the retired jobs and remove the installed copy of their plists.

    The running job is only unloaded for the real home: a temporary home (a
    proof or a test) never touches the jobs of the machine, it only removes
    the copy it holds. The real install finds the installed plist and
    unloads the job with it.

    Every step is best effort and every refusal is reported: a job that
    cannot be unloaded must be said out loud, not hidden."""
    notes: list[str] = []
    live = home == Path.home()
    for label in RETIRED_JOBS:
        plist = retired_plist(label, home)
        if not plist.is_file():
            continue
        if not live:
            notes.append(
                f"Removed {plist}. The running job was left alone: this is "
                "not the real home."
            )
        else:
            uid = os.getuid()
            code = run_status(["launchctl", "bootout", f"gui/{uid}/{label}"])
            if code == 0:
                notes.append(f"Unloaded the retired job {label}.")
            elif job_loaded(label):
                notes.append(
                    f"The retired job {label} is still loaded: launchctl "
                    f"bootout gui/{uid}/{label} did not work. Stop it by hand."
                )
            else:
                notes.append(f"The retired job {label} was not loaded.")
        try:
            plist.unlink()
        except OSError as exc:
            notes.append(f"Could not remove {plist}: {exc}")
            continue
        notes.append(f"Removed the retired job's plist {plist}.")
    return notes


def is_real_home(home: Path) -> bool:
    """Return True when home is the home of this user.

    A temporary home (a proof or a test) must never touch the jobs of the
    machine. The same rule retire_jobs follows decides here."""
    return home == Path.home()


def plist_label(data: bytes) -> str | None:
    """Return the launchd label of a rendered plist, or None when it has none."""
    try:
        parsed = plistlib.loads(data)
    except (plistlib.InvalidFileException, ExpatError, ValueError):
        return None
    label = parsed.get("Label")
    return label if isinstance(label, str) and label else None


def changed_launchd_jobs(
    pending: list[tuple[Path, bytes, int]]
) -> list[tuple[str | None, Path]]:
    """Return the launchd jobs whose plist this run changed.

    Only a plist that changed is a job to reload: a job whose installed file
    is already the wanted one keeps running what it runs."""
    jobs = []
    for target, data, _mode in pending:
        if target.parent.name != "LaunchAgents":
            continue
        jobs.append((plist_label(data), target))
    return jobs


def job_released(label: str, uid: int, timeout: float = 15.0) -> bool:
    """Wait until launchd lets go of the label, and say whether it did.

    launchd keeps the old service for a moment after the bootout. A
    bootstrap that arrives while the old service is still winding down is
    refused with "Operation already in progress", so waiting for the
    release belongs to the reload: the bootout and the bootstrap still run
    once each, and nothing is retried with other flags."""
    deadline = time.monotonic() + timeout
    while True:
        code = run_status(["launchctl", "print", f"gui/{uid}/{label}"])
        if code is None:
            return False
        if code != 0:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.2)


def reload_job(label: str, plist: Path, uid: int, timeout: float = 15.0) -> str:
    """Reload one launchd job and report what launchctl said.

    The job is booted out first, then bootstrapped from the written plist.
    A job that is not loaded says so, and that is not a refusal: the
    bootstrap alone is enough. A real refusal is reported with the text
    launchctl wrote, and is not retried with other flags."""
    code, error = run_status_text(["launchctl", "bootout", f"gui/{uid}/{label}"])
    if code is None:
        return f"Refused to reload the launchd job {label}: launchctl could not be run."
    if code != 0 and job_loaded(label):
        return (
            f"Refused to reload the launchd job {label}: launchctl bootout "
            f"gui/{uid}/{label} failed: {error}"
        )
    if not job_released(label, uid, timeout):
        return (
            f"Refused to reload the launchd job {label}: launchd kept the job "
            f"after the bootout, so the new plist was not loaded."
        )
    code, error = run_status_text(["launchctl", "bootstrap", f"gui/{uid}", str(plist)])
    if code == 0:
        return f"Reloaded the launchd job {label}."
    if job_loaded(label):
        return (
            f"Reloaded the launchd job {label}: launchd had loaded the new "
            f"plist itself."
        )
    return (
        f"Refused to reload the launchd job {label}: launchctl bootstrap "
        f"gui/{uid} {plist} failed: {error} The job is not loaded now."
    )


def reload_jobs(home: Path, jobs: list[tuple[str | None, Path]]) -> list[str]:
    """Reload the launchd jobs whose plist changed in this run.

    Only the real home touches the jobs of the machine: a temporary home
    writes its own files and leaves every running job alone, the same rule
    retire_jobs follows."""
    notes: list[str] = []
    if not is_real_home(home):
        for label, plist in jobs:
            name = label or plist.name
            notes.append(f"Skipped the reload of {name}: this is not the real home.")
        return notes
    uid = os.getuid()
    for label, plist in jobs:
        if label is None:
            notes.append(f"Refused to reload {plist}: the plist names no launchd job.")
            continue
        notes.append(reload_job(label, plist, uid))
    return notes


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


def changes(
    checkout: Path, home: Path, coordinator: Path | None = None
) -> list[tuple[Path, bytes, int]]:
    wanted = [
        (target, src.read_bytes(), mode) for src, target, mode in plan(checkout, home)
    ]
    wanted += [(target, data, 0o644) for data, target in render_plists(checkout, home)]
    shim = shim_item(checkout, home, os.environ.get("PATH", ""))
    if shim is not None:
        wanted.append(shim)
    router = home / TASK_ROUTER
    live_router = read_regular(router)
    if live_router is not None:
        text = task_router_text(live_router[0].decode(), *checkout_pi_models(checkout))
        wanted.append((router, text.encode(), stat.S_IMODE(live_router[1].st_mode)))
    tickets = home / ".coordinator/tickets.json"
    live_tickets = read_regular(tickets)
    if live_tickets is not None:
        stripped = without_old_lists(live_tickets[0])
        if stripped is not None:
            wanted.append((tickets, stripped, stat.S_IMODE(live_tickets[1].st_mode)))
    coordinator = coordinator or coordinator_dir(home)
    readme = checkout.joinpath("coordinator", *OVERNIGHT_README)
    if readme.is_file() and coordinator.is_dir():
        wanted.append(
            (overnight_root(coordinator) / "README.md", readme.read_bytes(), 0o644)
        )
    if coordinator.is_dir():
        source = checkout / HILLCLIMB_SOURCE
        for name in HILLCLIMB_FILES:
            wanted.append((coordinator / "evals/hillclimb" / name, (source / name).read_bytes(), 0o644))
        for name in LOOP_FILES:
            wanted.append((coordinator / "loop" / name, (checkout / LOOP_SOURCE / name).read_bytes(), 0o644))
    ignore = gitignore_item(coordinator)
    if ignore is not None:
        wanted.append((ignore[0], ignore[1], 0o644))
    pending = []
    for target, data, mode in wanted:
        current = read_regular(target)
        if (
            current is None or current[0] != data
            or stat.S_IMODE(current[1].st_mode) != mode
        ):
            pending.append((target, data, mode))
    return pending


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def recorded_mod_hashes(home: Path) -> dict[str, str]:
    receipt = read_regular(home / ".local/state/mac-ops" / RECEIPT_NAME)
    return json.loads(receipt[0]).get("mod_hashes", {}) if receipt else {}


def split_local_mods(
    pending: list[tuple[Path, bytes, int]], home: Path, recorded: dict[str, str]
) -> tuple[list[tuple[Path, bytes, int]], list[Path]]:
    mods = home / MODS_DIR
    rest, kept = [], []
    for item in pending:
        target, data, _ = item
        current = read_regular(target) if target.is_relative_to(mods) else None
        owned = recorded.get(str(target), digest(data))
        if current is not None and current[0] != data and digest(current[0]) != owned:
            kept.append(target)
        else:
            rest.append(item)
    return rest, kept


def ensure_overnight_dirs(coordinator: Path, home: Path) -> list[Path]:
    """Create the overnight folders. A refused directory is reported and left
    alone; it must not fail the rest of the install."""
    if not coordinator.is_dir():
        return []
    base = home if coordinator.is_relative_to(home) else coordinator
    created = []
    for directory in overnight_dirs(coordinator):
        if directory.is_dir():
            continue
        try:
            create_dir_chain(directory, base)
        except ValueError as exc:
            print(f"Warning: {exc}")
            continue
        created.append(directory)
    return created


def smoke_checks(home: Path) -> list[dict]:
    results = []
    # `alarms.py` is the command the coordinator panel runs when Shyam
    # answers an alarm, so the install checks that it runs.
    for name, argument in (("coordq", "status"), ("ticket", "--help"),
                           ("overnight", "--help"), ("alarms.py", "--help")):
        command = ["/opt/homebrew/bin/python3", str(home / ".local/bin" / name), argument]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30,
                                    env={**os.environ, "HOME": str(home)}, cwd=home)
            error = result.stderr.strip()
            healthy = result.returncode == 0
            if healthy and name == "coordq":
                try:
                    payload = json.loads(result.stdout)
                    healthy = isinstance(payload, dict) and "cap" in payload
                except ValueError:
                    healthy = False
                if not healthy:
                    error = "coordq status must return a JSON object with cap"
            results.append({"command": command, "healthy": healthy,
                            "returncode": result.returncode, "error": error})
        except (OSError, subprocess.TimeoutExpired) as exc:
            results.append({"command": command, "healthy": False, "error": str(exc)})
    return results


def require_healthy(home: Path) -> None:
    results = smoke_checks(home)
    if not all(result["healthy"] for result in results):
        raise RuntimeError("Coordinator smoke checks failed: " + json.dumps(results))


def restore_files(backups: Path) -> None:
    saved = read_regular(backups / "manifest.json")
    if saved is None:
        return
    failures = []
    for entry in reversed(json.loads(saved[0])["files"]):
        target = Path(entry["path"])
        try:
            if entry["backup"] is None:
                with safe_parent(target) as parent:
                    try:
                        os.unlink(target.name, dir_fd=parent)
                    except FileNotFoundError:
                        pass
            else:
                original = read_regular(backups / entry["backup"])
                if original is None:
                    raise RuntimeError("Missing backup: " + entry["backup"])
                atomic_write(target, original[0], entry["mode"])
                with safe_parent(target) as parent:
                    os.utime(target.name, dir_fd=parent,
                             ns=(entry["atime_ns"], entry["mtime_ns"]),
                             follow_symlinks=False)
        except (OSError, ValueError, RuntimeError) as exc:
            failures.append(f"{target}: {exc}")
    if failures:
        raise RuntimeError("Rollback incomplete: " + "; ".join(failures))


def require_main_source(checkout: Path) -> str:
    def git(*args: str) -> str:
        try:
            return subprocess.check_output(
                ["git", "-C", str(checkout), *args],
                stderr=subprocess.PIPE, text=True, timeout=60,
            ).strip()
        except (subprocess.SubprocessError, OSError) as exc:
            raise RuntimeError("Cannot verify installer source against origin/main") from exc

    top = Path(git("rev-parse", "--show-toplevel")).resolve()
    common = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
    if top != checkout.resolve() or common != top / ".git":
        raise RuntimeError("Installation requires the canonical checkout, not a linked worktree")
    if git("symbolic-ref", "--short", "HEAD") != "main":
        raise RuntimeError("Installation requires branch main")
    if git("status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError("Installation requires a clean checkout")
    git("fetch", "origin", "+refs/heads/main:refs/remotes/origin/main")
    head = git("rev-parse", "HEAD")
    if head != git("rev-parse", "refs/remotes/origin/main"):
        raise RuntimeError("Installation requires HEAD matching fetched origin/main")
    return head


def manifest_hashes(checkout: Path) -> dict[str, str]:
    root = checkout / "coordinator"
    arms = json.loads((root / "config" / "factory.json").read_text())["arms"]
    return {
        arm: hashlib.sha256(b"".join((root / name).read_bytes() for name in names)).hexdigest()
        for arm, names in arms.items()
    }


def install(
    checkout: Path,
    dry_run: bool,
    home: Path | None = None,
    coordinator: Path | None = None,
    overwrite_local_mods: bool = False,
) -> None:
    source_sha = require_main_source(checkout)
    require_real_home()
    home = home or Path.home()
    coordinator = coordinator or coordinator_dir(home)
    pending = changes(checkout, home, coordinator)
    state = home / ".local/state/mac-ops"
    receipt_target = state / RECEIPT_NAME
    # Validate the receipt before any installation writes, even on a no-op.
    read_regular(receipt_target)
    recorded = recorded_mod_hashes(home)
    kept: list[Path] = []
    if not overwrite_local_mods:
        pending, kept = split_local_mods(pending, home, recorded)
    mod_hashes = {
        **recorded,
        **{
            str(target): digest(source.read_bytes())
            for source, target, _ in plan(checkout, home)
            if target.is_relative_to(home / MODS_DIR) and target not in kept
        },
    }
    if dry_run:
        print(json.dumps(
            {
                "action": "coordinator",
                "would_write": [str(t) for t, _, _ in pending],
                "kept_local": [str(t) for t in kept],
                "would_retire": [str(path) for path in retired_plists(home)],
                "would_archive": [str(path) for path in old_list_files(home)],
                "would_reload": [
                    label or str(target)
                    for label, target in changed_launchd_jobs(pending)
                ],
                "overnight_root": str(overnight_root(coordinator)),
                "would_create": [
                    str(d) for d in overnight_dirs(coordinator) if not d.is_dir()
                ],
            },
            indent=2,
        ))
        return
    for note in retire_jobs(home):
        print(note)
    for path in archive_model_lists(home):
        print(f"Archived model list: {path}")
    created, _refused = ensure_log_dirs(log_dirs(render_plists(checkout, home)), home)
    for directory in created:
        print(f"Created log directory: {directory}")
    for directory in ensure_overnight_dirs(coordinator, home):
        print(f"Created overnight directory: {directory}")
    if not coordinator.is_dir():
        print(
            f"Warning: coordinator folder {coordinator} does not exist. "
            "The overnight layout was not created. Point the installer at "
            "one with --coordinator-dir."
        )
    for pid in manual_monitors():
        print(
            f"Warning: a hand-started turn-cap monitor is running (pid {pid}). "
            f"Stop it so only one monitor runs: kill {pid}"
        )
    for target in kept:
        print(f"Kept local edit: {target}")
    if not pending and mod_hashes == recorded:
        require_healthy(home)
        print("Wrote 0 coordinator files. Already in sync and healthy.")
        return
    transaction = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex
    backups = state / "coordinator-backups" / transaction
    # Reserve a unique transaction using the same no-follow directory walk.
    with safe_parent(backups / "manifest.json", create=True):
        pass
    print(f"Backup transaction: {backups}", flush=True)
    try:
        for target, data, mode in pending:
            write(target, data, mode, backups)
        receipt = {
            "checkout": str(checkout),
            "source_sha": source_sha,
            "installed_at": time.time(),
            "written": [str(t) for t, _, _ in pending],
            "mod_hashes": mod_hashes,
            "manifest": manifest_hashes(checkout),
            "backups": str(backups),
        }
        write(receipt_target, json.dumps(receipt).encode(), 0o600, backups)
        require_healthy(home)
    except (OSError, ValueError, RuntimeError) as exc:
        restore_files(backups)
        raise RuntimeError(f"{exc}; replaced files rolled back") from exc
    print(f"Wrote {len(pending)} coordinator files. Backups: {backups}")
    for note in reload_jobs(home, changed_launchd_jobs(pending)):
        print(note)


def flatten_keys(node: dict, prefix: str = "") -> dict:
    flat = {}
    for key, value in node.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(flatten_keys(value, f"{path}."))
        else:
            flat[path] = value
    return flat


def config_key_drift(checkout: Path, home: Path) -> list[str]:
    live_file = home / ".coordinator" / "tickets.json"
    if not live_file.exists():
        return []
    repo = flatten_keys(json.loads((checkout / "coordinator/config/tickets.json").read_text()))
    live = flatten_keys(json.loads(live_file.read_text()))
    return [
        path
        for path, value in repo.items()
        if path not in live
        or (path.startswith("repos.") and not path.endswith(".projectId") and live[path] != value)
    ]


def raise_walk_error(error: OSError) -> None:
    raise error


def unsourced_code(checkout: Path, coordinator: Path) -> list[str]:
    found = []
    for folder, dirs, files in os.walk(coordinator, onerror=raise_walk_error):
        dirs[:] = sorted(d for d in dirs if d not in DRIFT_SKIP_DIRS and not d.startswith("."))
        for name in sorted(files):
            if not name.endswith(DRIFT_CODE_SUFFIXES):
                continue
            if any(fnmatch.fnmatch(name, pattern) for pattern in LOCAL_ONLY_CODE):
                continue
            relative = (Path(folder) / name).relative_to(coordinator)
            if not (checkout / "coordinator" / relative).is_file():
                found.append(str(relative))
    return found


def status(checkout: Path, coordinator: Path | None = None, smoke: bool = True) -> None:
    home = Path.home()
    coordinator = coordinator or coordinator_dir(home)
    pending = changes(checkout, home, coordinator)
    _, kept = split_local_mods(pending, home, recorded_mod_hashes(home))
    missing = [d for d in overnight_dirs(coordinator) if not d.is_dir()]
    retired = [str(path) for path in retired_plists(home)] + [
        str(path) for path in retired_files(coordinator)
    ]
    unsourced = unsourced_code(checkout, coordinator)
    checks = smoke_checks(home) if smoke else []
    print(
        json.dumps(
            {
                "in_sync": not pending and not missing and not retired and not unsourced,
                "healthy": all(check["healthy"] for check in checks),
                "smoke_checks": checks,
                "differs": [str(t) for t, _, _ in pending],
                "config_key_drift": config_key_drift(checkout, home),
                "kept_local": [str(t) for t in kept],
                "locally_owned": [
                    str(home / ".coordinator" / name)
                    for name in LOCAL_CONFIG_FILES
                    if (home / ".coordinator" / name).exists()
                ],
                "overnight_root": str(overnight_root(coordinator)),
                "overnight_missing": [str(d) for d in missing],
                "retired_jobs": list(RETIRED_JOBS),
                "retired_leftovers": retired,
                "unsourced_code": unsourced,
            },
            indent=2,
        )
    )
    if unsourced:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("install", "status"), nargs="?", default="install"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-smoke", action="store_true", help="status only: skip the smoke checks")
    parser.add_argument(
        "--overwrite-local-mods",
        action="store_true",
        help="Overwrite Herdr mod files edited locally since the last install",
    )
    parser.add_argument(
        "--coordinator-dir",
        help="Coordinator runtime folder that holds the overnight layout",
    )
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parent
    coordinator = coordinator_dir(Path.home(), args.coordinator_dir)
    if args.action == "status":
        status(checkout, coordinator, not args.no_smoke)
        return
    if not args.dry_run and sys.platform != "darwin":
        raise RuntimeError("Coordinator install requires macOS")
    install(
        checkout, args.dry_run, coordinator=coordinator,
        overwrite_local_mods=args.overwrite_local_mods,
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as exc:
        print("mac-ops: " + str(exc), file=sys.stderr)
        sys.exit(1)
