#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Any

DEFAULT_CODE_ROOT = Path.home() / "Code"
DEFAULT_STATE_ROOT = Path.home() / ".local/state/mac-ops/worktree-cleaner"
DEFAULT_T3_DB = Path.home() / ".t3/userdata/statev2.sqlite"
NONTERMINAL = {"queued", "preparing", "starting", "running", "waiting", "active", "busy", "pending"}
TERMINAL_OR_IDLE = {"completed", "failed", "interrupted", "cancelled", "stopped", "idle", "ready", "resolved", "closed", "expired", "delivered", "committed"}
STATUS_TABLES = (
    ("orchestration_v2_projection_runs", "thread_id", "status"),
    ("orchestration_v2_projection_provider_threads", "thread_id", "status"),
    ("orchestration_v2_projection_provider_sessions", "thread_id", "status"),
    ("orchestration_v2_projection_runtime_requests", "thread_id", "status"),
    ("orchestration_v2_projection_subagents", "thread_id", "status"),
)
SKIP_DIRS = {".git", "node_modules", "vendor", "Pods", ".venv", "venv", "__pycache__", "DerivedData"}
SHA_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")


class SafetyError(RuntimeError):
    pass


def run(argv: list[str], *, cwd: Path | None = None, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SafetyError(f"command_unavailable:{Path(argv[0]).name}") from exc


def git(root: Path, *args: str, timeout: int = 30) -> str:
    result = run(["git", "-C", str(root), *args], timeout=timeout)
    if result.returncode != 0:
        raise SafetyError(f"git_{args[0].replace('-', '_')}_failed")
    return result.stdout


def canonical(path: str | Path) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(path)))


def inside(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((canonical(path), canonical(root))) == canonical(root)
    except ValueError:
        return False


def excluded_repo(root: Path, repo_slug: str | None = None) -> bool:
    parts = {part.casefold() for part in root.parts}
    remote_parts = {part.casefold() for part in repo_slug.split("/")} if repo_slug else set()
    identities = parts | remote_parts
    if "srw" in identities or any(part.startswith("srw-") for part in identities) or any("strategy-replay-workbench" in part for part in identities):
        return True
    if "slash-eureka" in parts and ("dbt" in parts or "omni" in parts or root.name.casefold() == "slash-eureka"):
        return True
    if "slash-eureka" in remote_parts and remote_parts.intersection({"dbt", "omni"}):
        return True
    if any("slash-eureka" in part and (part.endswith("-dbt") or part.endswith("-omni")) for part in remote_parts):
        return True
    return False


def discover_repositories(code_root: Path) -> list[Path]:
    if not code_root.is_dir() or code_root.is_symlink():
        raise SafetyError("code_root_unavailable")
    found: set[str] = set()
    errors: list[str] = []

    def onerror(exc: OSError) -> None:
        errors.append(type(exc).__name__)

    for current, dirs, _files in os.walk(code_root, topdown=True, followlinks=False, onerror=onerror):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS and not (Path(current) / name).is_symlink()]
        root = Path(current)
        marker = root / ".git"
        if marker.is_dir() and not marker.is_symlink() and (marker / "HEAD").is_file():
            found.add(canonical(root))
        dirs[:] = [name for name in dirs if name != ".git"]
    if errors:
        raise SafetyError("repository_scan_incomplete")
    return [Path(item) for item in sorted(found)]


def worktrees(repo: Path) -> list[dict[str, Any]]:
    output = git(repo, "worktree", "list", "--porcelain", "-z")
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for field in output.split("\0"):
        if not field:
            if current:
                entries.append(current)
                current = {}
            continue
        if field.startswith("worktree "):
            if current:
                entries.append(current)
            current = {"path": field[len("worktree "):], "locked": False, "detached": False, "bare": False}
        elif field == "detached":
            current["detached"] = True
        elif field == "bare":
            current["bare"] = True
        elif field.startswith("HEAD "):
            current["head"] = field[len("HEAD "):]
        elif field.startswith("branch "):
            current["branch"] = field[len("branch "):].removeprefix("refs/heads/")
        elif field.startswith("locked"):
            current["locked"] = True
        elif field.startswith("prunable"):
            current["prunable"] = True
    if not entries:
        raise SafetyError("worktree_inventory_empty")
    return entries


def status_for(path: Path) -> tuple[bool, str]:
    output = git(path, "status", "--porcelain=v1", "--untracked-files=all")
    return bool(output.strip()), output.strip()


def detached_idle_seconds(path: Path) -> int | None:
    marker = path / ".git"
    if marker.is_symlink() or not marker.is_file():
        return None
    value = marker.read_text(encoding="utf-8").strip()
    if not value.startswith("gitdir: "):
        return None
    admin = Path(value[len("gitdir: "):])
    if not admin.is_absolute():
        admin = path / admin
    admin = admin.resolve()
    common = Path(git(path, "rev-parse", "--git-common-dir").strip())
    if not common.is_absolute():
        common = path / common
    if admin.parent.resolve() != (common.resolve() / "worktrees"):
        return None
    log = admin / "logs/HEAD"
    if log.is_symlink() or not log.is_file():
        return None
    stamps: list[int] = []
    for line in log.read_text(encoding="utf-8").splitlines():
        fields = line.partition("\t")[0].split()
        if len(fields) >= 4 and fields[-2].isdigit():
            stamps.append(int(fields[-2]))
    return int(time.time()) - max(stamps) if stamps else None


def _read_status_table(conn: sqlite3.Connection, table: str, thread_column: str, status_column: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for row in conn.execute(f'SELECT "{thread_column}", "{status_column}" FROM "{table}"'):
        thread_id, status = row
        if not isinstance(thread_id, str) or not isinstance(status, str) or not status:
            raise SafetyError("t3_status_shape_invalid")
        result.setdefault(thread_id, []).append(status.casefold())
    return result


class T3State:
    def __init__(self, path: Path):
        if path.is_symlink() or not path.is_file():
            raise SafetyError("t3_state_unavailable")
        uri = path.resolve().as_uri() + "?mode=ro"
        try:
            self.conn = sqlite3.connect(uri, uri=True, timeout=5)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("BEGIN")
            tables = {row[0] for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            required = {"orchestration_v2_projection_threads", "orchestration_v2_projection_metadata", *(item[0] for item in STATUS_TABLES), "orchestration_v2_thread_launch_workflows"}
            if not required.issubset(tables):
                raise SafetyError("t3_state_schema_unrecognized")
            metadata = self.conn.execute("SELECT schema_version FROM orchestration_v2_projection_metadata").fetchall()
            if not metadata or any(not isinstance(row[0], int) or row[0] not in {1, 2} for row in metadata):
                raise SafetyError("t3_state_version_unrecognized")
            thread_rows = self.conn.execute("SELECT thread_id, payload_json FROM orchestration_v2_projection_threads").fetchall()
            if not thread_rows:
                raise SafetyError("t3_state_empty")
            self.paths: dict[str, list[str]] = {}
            self.thread_status: dict[str, list[str]] = {}
            for row in thread_rows:
                try:
                    payload = json.loads(row["payload_json"])
                except (TypeError, json.JSONDecodeError) as exc:
                    raise SafetyError("t3_thread_projection_invalid") from exc
                if not isinstance(payload, dict):
                    raise SafetyError("t3_thread_projection_invalid")
                path_value = payload.get("worktreePath")
                if path_value is not None:
                    if not isinstance(path_value, str) or not path_value:
                        raise SafetyError("t3_worktree_path_invalid")
                    self.paths.setdefault(canonical(path_value), []).append(row["thread_id"])
            for table, thread_column, status_column in STATUS_TABLES:
                statuses = _read_status_table(self.conn, table, thread_column, status_column)
                for thread_id, values in statuses.items():
                    self.thread_status.setdefault(thread_id, []).extend(values)
            workflow_rows = self.conn.execute("SELECT worktree_path, status FROM orchestration_v2_thread_launch_workflows").fetchall()
            self.workflows: dict[str, list[str]] = {}
            for row in workflow_rows:
                if row["worktree_path"]:
                    if not isinstance(row["worktree_path"], str) or not isinstance(row["status"], str):
                        raise SafetyError("t3_launch_workflow_invalid")
                    self.workflows.setdefault(canonical(row["worktree_path"]), []).append(row["status"].casefold())
            self.conn.close()
        except (sqlite3.Error, OSError) as exc:
            raise SafetyError("t3_state_read_failed") from exc

    def blockers(self, path: Path) -> list[str]:
        path_key = canonical(path)
        reasons: list[str] = []
        for thread_id in self.paths.get(path_key, []):
            statuses = self.thread_status.get(thread_id, [])
            if not statuses:
                reasons.append("t3_status_unknown")
            for status in statuses:
                if status in NONTERMINAL:
                    reasons.append("t3_thread_active")
                elif status not in TERMINAL_OR_IDLE:
                    reasons.append("t3_status_unknown")
        for status in self.workflows.get(path_key, []):
            if status in NONTERMINAL:
                reasons.append("t3_launch_in_progress")
            elif status not in TERMINAL_OR_IDLE:
                reasons.append("t3_launch_status_unknown")
        return sorted(set(reasons))


class GitHub:
    def __init__(self):
        self.repos: dict[str, str | None] = {}
        self.commits: dict[tuple[str, str], bool] = {}
        self.pull_requests: dict[tuple[str, str, str], list[dict[str, Any]] | None] = {}

    def repo(self, root: Path, *, refresh: bool = False) -> str | None:
        key = canonical(root)
        if key in self.repos and not refresh:
            return self.repos[key]
        try:
            result = run(["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], cwd=root)
        except SafetyError:
            result = None
        value = result.stdout.strip() if result else ""
        if result is None or result.returncode != 0 or not re.fullmatch(r"[^/\s]+/[^/\s]+", value):
            self.repos[key] = None
        else:
            self.repos[key] = value
        return self.repos[key]

    def commit_present(self, repo: str, sha: str, *, refresh: bool = False) -> bool:
        key = (repo, sha.lower())
        if key in self.commits and not refresh:
            return self.commits[key]
        if not SHA_RE.fullmatch(sha):
            self.commits[key] = False
            return False
        try:
            result = run(["gh", "api", f"repos/{repo}/commits/{sha}", "--jq", ".sha"])
            self.commits[key] = result.returncode == 0 and result.stdout.strip().lower() == sha.lower()
        except SafetyError:
            self.commits[key] = False
        return self.commits[key]

    def prs(self, repo: str, branch: str, *, refresh: bool = False) -> list[dict[str, Any]] | None:
        owner = repo.split("/", 1)[0]
        key = (repo, owner, branch)
        if key in self.pull_requests and not refresh:
            return self.pull_requests[key]
        try:
            result = run([
                "gh", "pr", "list", "--repo", repo, "--head", branch,
                "--state", "all", "--limit", "1000", "--json", "number,state,headRefName,headRefOid",
            ])
        except SafetyError:
            result = None
        if result is None or result.returncode != 0:
            self.pull_requests[key] = None
        else:
            try:
                value = json.loads(result.stdout)
                if not isinstance(value, list) or len(value) >= 1000 or any(not isinstance(row, dict) for row in value):
                    raise ValueError
                self.pull_requests[key] = value
            except (ValueError, json.JSONDecodeError):
                self.pull_requests[key] = None
        return self.pull_requests[key]


def verify_pr(github: GitHub, repo: str | None, branch: str | None, head: str, *, refresh: bool = False) -> tuple[bool, str | None, str | None]:
    if not repo or not branch:
        return False, "github_repository_unknown", None
    prs = github.prs(repo, branch, refresh=refresh)
    if prs is None:
        return False, "github_pr_state_unavailable", None
    matching = [row for row in prs if row.get("headRefName") == branch]
    if any(str(row.get("state", "")).upper() == "OPEN" for row in matching):
        return False, "github_pr_open", None
    closed = [row for row in matching if str(row.get("state", "")).upper() in {"CLOSED", "MERGED"} and str(row.get("headRefOid", "")).lower() == head.lower()]
    if not closed:
        return False, "github_pr_not_closed_for_head", None
    row = closed[-1]
    return True, None, f"https://github.com/{repo}/pull/{row.get('number')}"


def evaluate(repo_root: Path, record: dict[str, Any], code_root: Path, t3_db: Path, github: GitHub, *, refresh: bool = False, t3_state: T3State | None = None) -> dict[str, Any]:
    path = Path(record["path"])
    result: dict[str, Any] = {
        "repo": str(repo_root), "path": str(path), "branch": record.get("branch"),
        "head": record.get("head"), "detached": bool(record.get("detached")),
        "main_checkout": canonical(path) == canonical(repo_root), "dirty": None,
        "remote_commit_present": None, "pull_request": None, "eligible": False, "reasons": [],
    }
    reasons: list[str] = []
    if not inside(repo_root, code_root):
        reasons.append("repository_outside_code_root")
    if result["main_checkout"] or record.get("bare"):
        reasons.append("main_checkout")
    if not any(inside(path, root) for root in (code_root / ".worktrees", Path("/private/tmp"), Path("/tmp"))):
        reasons.append("worktree_outside_scope")
    if reasons:
        result["reasons"] = reasons
        return result
    if record.get("locked"):
        reasons.append("worktree_locked")
    if record.get("prunable") or not path.is_dir():
        reasons.append("worktree_missing_or_prunable")
    if not SHA_RE.fullmatch(str(record.get("head") or "")):
        reasons.append("head_unknown")
    if path.is_dir():
        try:
            root = Path(git(path, "rev-parse", "--show-toplevel").strip())
            if canonical(root) != canonical(path):
                reasons.append("worktree_root_mismatch")
            dirty, _ = status_for(path)
            result["dirty"] = dirty
            if dirty:
                reasons.append("worktree_dirty")
        except SafetyError:
            reasons.append("worktree_status_unknown")
    repo_slug = github.repo(repo_root, refresh=refresh)
    if not repo_slug:
        reasons.append("github_repository_unknown")
    elif SHA_RE.fullmatch(str(record.get("head") or "")):
        present = github.commit_present(repo_slug, record["head"], refresh=refresh)
        result["remote_commit_present"] = present
        if not present:
            reasons.append("remote_commit_unverified")
    if record.get("detached"):
        try:
            idle = detached_idle_seconds(path) if path.is_dir() else None
        except SafetyError:
            idle = None
        result["detached_idle_seconds"] = idle
        if idle is None or idle < 24 * 60 * 60:
            reasons.append("detached_not_proven_24h_old")
    elif not result["main_checkout"]:
        ok, why, pr_url = verify_pr(github, repo_slug, record.get("branch"), str(record.get("head") or ""), refresh=refresh)
        result["pull_request"] = pr_url
        if not ok and why:
            reasons.append(why)
    try:
        t3 = t3_state if t3_state is not None else T3State(t3_db)
        reasons.extend(t3.blockers(path))
    except SafetyError as exc:
        reasons.append(str(exc))
    result["reasons"] = sorted(set(reasons))
    result["eligible"] = not result["reasons"]
    return result


def inventory(code_root: Path, t3_db: Path, github: GitHub, t3_state: T3State) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    excluded = 0
    for repo_root in discover_repositories(code_root):
        repo_slug = github.repo(repo_root)
        if excluded_repo(repo_root, repo_slug):
            excluded += 1
            continue
        records = worktrees(repo_root)
        for record in records:
            row = evaluate(repo_root, record, code_root, t3_db, github, t3_state=t3_state)
            rows.append(row)
    return rows, excluded


def report_day() -> str:
    return dt.datetime.now().astimezone().date().isoformat()


def secure_state_dir(path: Path) -> Path:
    path = path.expanduser()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise SafetyError("unsafe_state_directory")
    return path


def atomic_write(path: Path, value: str) -> None:
    fd, name = tempfile.mkstemp(prefix=".worktree-cleaner-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_daily_report(code_root: Path, rows: list[dict[str, Any]], summary: dict[str, Any], dry_run: bool) -> Path:
    day = report_day()
    flagged = [row for row in rows if not row["main_checkout"] and "worktree_outside_scope" not in row["reasons"] and (row.get("dirty") is not False or row.get("remote_commit_present") is not True)]
    lines = [
        f"# Dirty and unverified worktrees, {day}",
        "",
        f"Last scan: {dt.datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"Mode: {'dry-run' if dry_run else 'apply'}",
        "",
        "## Counts",
        "",
        f"- Repositories scanned: {summary['repositories_scanned']}",
        f"- Worktrees scanned: {summary['worktrees_scanned']}",
        f"- Eligible: {summary['eligible']}",
        f"- Removed: {summary['removed']}",
        f"- Excluded repositories: {summary['excluded_repositories']}",
        "",
        "## Dirty or unverified worktrees",
        "",
    ]
    if not flagged:
        lines.append("No dirty worktrees or commits missing remote proof were found.")
    for row in flagged:
        state = "dirty" if row.get("dirty") is True else "clean" if row.get("dirty") is False else "status unverified"
        if row.get("remote_commit_present") is not True:
            state += ", remote commit unverified"
        lines.append(f"- `{row['path']}` ({row['branch'] or 'detached'}, {state})")
        if row.get("reasons"):
            lines.append(f"  Reasons: {', '.join(row['reasons'])}")
    report_dir = code_root / "coordinator" / "evidence"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"worktrees-kept-{day}.md"
    atomic_write(path, "\n".join(lines) + "\n")
    return path


def append_removal(state_root: Path, row: dict[str, Any], event: str) -> None:
    path = state_root.parent / "worktree-cleaner.log"
    if path.is_symlink():
        raise SafetyError("unsafe_removal_log")
    entry = {
        "event": event,
        "removed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repo": row["repo"], "path": row["path"], "branch": row["branch"],
        "head": row["head"], "pull_request": row["pull_request"],
        "reason": "clean, remote commit verified, no active T3 work, and closed PR or detached idle for 24 hours",
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as output:
        output.write(json.dumps(entry, sort_keys=True) + "\n")
        output.flush()
        os.fsync(output.fileno())


def scan(code_root: Path, t3_db: Path, state_root: Path, apply: bool) -> dict[str, Any]:
    state_root = secure_state_dir(state_root)
    lock_path = state_root / "cleaner.lock"
    if lock_path.is_symlink():
        raise SafetyError("unsafe_lock_file")
    with lock_path.open("a+") as lock:
        os.chmod(lock_path, 0o600)
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SafetyError("cleaner_already_running") from exc
        if not t3_db.is_file() or t3_db.is_symlink():
            raise SafetyError("t3_state_unavailable")
        initial_state = T3State(t3_db)
        github = GitHub()
        rows, excluded = inventory(code_root, t3_db, github, initial_state)
        eligible = [row for row in rows if row["eligible"]]
        removed = 0
        if apply:
            for candidate in eligible:
                repo_root = Path(candidate["repo"])
                current = next((r for r in worktrees(repo_root) if canonical(r["path"]) == canonical(candidate["path"])), None)
                if current is None:
                    candidate["eligible"] = False
                    candidate["reasons"] = ["worktree_registration_changed"]
                    continue
                final = evaluate(repo_root, current, code_root, t3_db, github, refresh=True)
                if current.get("head") != candidate.get("head") or current.get("branch") != candidate.get("branch"):
                    final["eligible"] = False
                    final["reasons"] = sorted(set(final["reasons"] + ["worktree_changed_after_scan"]))
                if not final["eligible"]:
                    candidate.update(final)
                    continue
                try:
                    latest_head = git(Path(candidate["path"]), "rev-parse", "HEAD").strip()
                    latest_dirty, _ = status_for(Path(candidate["path"]))
                except SafetyError:
                    latest_head = ""
                    latest_dirty = True
                if latest_head.lower() != str(candidate["head"]).lower() or latest_dirty:
                    candidate["eligible"] = False
                    candidate["reasons"] = ["worktree_changed_before_remove"]
                    continue
                append_removal(state_root, candidate, "removal_attempted")
                try:
                    result = run(["git", "-C", str(repo_root), "worktree", "remove", candidate["path"]], timeout=300)
                except SafetyError:
                    append_removal(state_root, candidate, "removal_outcome_unknown")
                    candidate["eligible"] = False
                    candidate["reasons"] = ["worktree_remove_outcome_unknown"]
                    continue
                if result.returncode != 0 or Path(candidate["path"]).exists():
                    append_removal(state_root, candidate, "removal_failed")
                    candidate["eligible"] = False
                    candidate["reasons"] = ["worktree_remove_failed"]
                    continue
                append_removal(state_root, candidate, "removed")
                candidate["eligible"] = False
                candidate["removed"] = True
                removed += 1
                try:
                    git(repo_root, "worktree", "prune")
                except SafetyError:
                    append_removal(state_root, candidate, "prune_failed")
        summary = {
            "mode": "apply" if apply else "dry-run",
            "repositories_scanned": len({row["repo"] for row in rows}),
            "worktrees_scanned": len(rows),
            "eligible": sum(1 for row in rows if row["eligible"]),
            "removed": removed,
            "held": sum(1 for row in rows if not row["eligible"] and not row.get("removed")),
            "excluded_repositories": excluded,
            "held_reasons": {},
        }
        summary["per_repo"] = {}
        for row in rows:
            if not row["main_checkout"]:
                counts = summary["per_repo"].setdefault(row["repo"], {"would_remove": 0, "kept_dirty": 0, "kept_unpushed": 0, "in_use": 0})
                counts["would_remove"] += int(row["eligible"])
                counts["kept_dirty"] += int(row["dirty"] is True)
                counts["kept_unpushed"] += int(row["remote_commit_present"] is False)
                counts["in_use"] += int(any(reason in row["reasons"] for reason in ("t3_thread_active", "t3_launch_in_progress")))
            for reason in row.get("reasons", []):
                summary["held_reasons"][reason] = summary["held_reasons"].get(reason, 0) + 1
        report = write_daily_report(code_root, rows, summary, dry_run=not apply)
        summary["daily_report"] = str(report)
        summary["rows"] = rows
        return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely review and remove eligible Git worktrees under repositories in ~/Code.")
    parser.add_argument("--code-root", type=Path, default=DEFAULT_CODE_ROOT)
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    parser.add_argument("--t3-db", type=Path, default=Path(os.environ.get("T3_STATE_DB", DEFAULT_T3_DB)))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="remove only worktrees that pass every safety check")
    mode.add_argument("--dry-run", action="store_false", dest="apply", help="report counts without removing worktrees")
    parser.set_defaults(apply=False)
    args = parser.parse_args(argv)
    try:
        result = scan(args.code_root.expanduser(), args.t3_db.expanduser(), args.state_root.expanduser(), args.apply)
    except SafetyError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
