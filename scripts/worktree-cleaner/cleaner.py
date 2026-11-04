#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re

import subprocess
import sys
import tempfile
import time
from typing import Any

DEFAULT_CODE_ROOT = Path.home() / "Code"
DEFAULT_STATE_ROOT = Path.home() / ".local/state/mac-ops/worktree-cleaner"

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


class EmpryoState:
    PAGE_LIMIT = 100
    MAX_PAGES = 1000
    FINISHED_STATUSES = {"completed", "interrupted", "failed", "cancelled", "rolled_back"}

    def __init__(self):
        self._read_pages()
        first_records = self.records
        first_pages = self.page_count
        self._read_pages()
        if self.records != first_records:
            raise SafetyError("empryo_list_changed")
        self.page_count += first_pages

    def _read_pages(self) -> None:
        self.records: dict[str, tuple[Any, ...]] = {}
        self.paths: list[tuple[Path, str]] = []
        self.thread_count = 0
        self.unfinished_count = 0
        self.page_count = 0
        seen: set[str] = set()
        cursor = 0
        total: int | None = None
        while self.page_count < self.MAX_PAGES:
            args = {"allProjects": True, "limit": self.PAGE_LIMIT, "cursor": cursor}
            result = run(["emp", "call", "emp_thread_list", json.dumps(args)])
            if result.returncode != 0:
                raise SafetyError("empryo_hub_unavailable")
            try:
                page = json.loads(result.stdout)
            except (ValueError, TypeError) as exc:
                raise SafetyError("empryo_list_invalid") from exc
            if not isinstance(page, dict) or "projectId" not in page or page["projectId"] is not None:
                raise SafetyError("empryo_all_projects_unverified")
            rows = page.get("threads")
            page_total = page.get("total")
            if not isinstance(rows, list) or len(rows) > self.PAGE_LIMIT or type(page_total) is not int or page_total < 0:
                raise SafetyError("empryo_list_invalid")
            if total is not None and page_total != total:
                raise SafetyError("empryo_list_changed")
            total = page_total
            self.page_count += 1
            for thread in rows:
                if not isinstance(thread, dict):
                    raise SafetyError("empryo_thread_invalid")
                thread_id = thread.get("threadId")
                status = thread.get("status")
                settled = thread.get("settled")
                pending = thread.get("pendingRequestCount")
                if not isinstance(thread_id, str) or not thread_id or thread_id in seen:
                    raise SafetyError("empryo_list_duplicate_or_invalid_thread")
                if not isinstance(status, str) or not status or type(settled) is not bool or type(pending) is not int or pending < 0:
                    raise SafetyError("empryo_thread_invalid")
                if "activeRunId" not in thread or (thread["activeRunId"] is not None and not isinstance(thread["activeRunId"], str)):
                    raise SafetyError("empryo_thread_invalid")
                seen.add(thread_id)
                finished = settled and status in self.FINISHED_STATUSES and thread["activeRunId"] is None and pending == 0
                thread_paths = []
                for key in ("worktreePath", "cwd"):
                    if key not in thread:
                        raise SafetyError("empryo_thread_path_unverified")
                    value = thread[key]
                    if value is not None:
                        if not isinstance(value, str) or not value or "\0" in value or not Path(value).is_absolute():
                            raise SafetyError("empryo_thread_path_invalid")
                        thread_paths.append(Path(canonical(value)))
                self.records[thread_id] = (status, settled, thread["activeRunId"], pending, tuple(sorted(str(path) for path in set(thread_paths))))
                if not finished:
                    if not thread_paths:
                        raise SafetyError("empryo_thread_path_unverified")
                    self.unfinished_count += 1
                    self.paths.extend((path, thread_id) for path in set(thread_paths))
            self.thread_count = len(seen)
            if "nextCursor" not in page or self.thread_count > total:
                raise SafetyError("empryo_list_incomplete")
            next_cursor = page["nextCursor"]
            if next_cursor is None:
                if self.thread_count != total:
                    raise SafetyError("empryo_list_incomplete")
                return
            if not rows or type(next_cursor) is not int or next_cursor != cursor + len(rows) or self.thread_count >= total:
                raise SafetyError("empryo_list_incomplete")
            cursor = next_cursor
        raise SafetyError("empryo_list_incomplete")

    def users(self, path: Path) -> list[str]:
        return sorted({thread_id for thread_path, thread_id in self.paths if inside(thread_path, path)})

    def blockers(self, path: Path) -> list[str]:
        return ["empryo_thread_unfinished"] if self.users(path) else []


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


def evaluate(repo_root: Path, record: dict[str, Any], code_root: Path, github: GitHub, emp_state: EmpryoState, *, refresh: bool = False) -> dict[str, Any]:
    path = Path(record["path"])
    result: dict[str, Any] = {
        "repo": str(repo_root), "path": str(path), "branch": record.get("branch"),
        "head": record.get("head"), "detached": bool(record.get("detached")),
        "main_checkout": canonical(path) == canonical(repo_root), "dirty": None,
        "remote_commit_present": None, "pull_request": None, "eligible": False, "reasons": [],
    }
    reasons = emp_state.blockers(path)
    result["empryo_threads"] = emp_state.users(path)
    if not inside(repo_root, code_root):
        reasons.append("repository_outside_code_root")
    if result["main_checkout"] or record.get("bare"):
        reasons.append("main_checkout")
    if not any(inside(path, root) for root in (code_root / ".worktrees", Path("/private/tmp"), Path("/tmp"))):
        reasons.append("worktree_outside_scope")
    if any(reason != "empryo_thread_unfinished" for reason in reasons):
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
    result["reasons"] = sorted(set(reasons))
    result["eligible"] = not result["reasons"]
    return result


def inventory(code_root: Path, github: GitHub, emp_state: EmpryoState) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    excluded = 0
    for repo_root in discover_repositories(code_root):
        repo_slug = github.repo(repo_root)
        if excluded_repo(repo_root, repo_slug):
            excluded += 1
            continue
        records = worktrees(repo_root)
        for record in records:
            row = evaluate(repo_root, record, code_root, github, emp_state)
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
    lines.extend(["", "## Empryo-held worktrees", ""])
    for row in rows:
        if row.get("empryo_threads"):
            lines.append(f"- `{row['path']}`: {', '.join(row['empryo_threads'])}")
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
        "reason": "clean, remote commit verified, no unfinished Empryo thread, and closed PR or detached idle for 24 hours",
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as output:
        output.write(json.dumps(entry, sort_keys=True) + "\n")
        output.flush()
        os.fsync(output.fileno())


def scan(code_root: Path, state_root: Path, apply: bool) -> dict[str, Any]:
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
        initial_state = EmpryoState()
        github = GitHub()
        rows, excluded = inventory(code_root, github, initial_state)
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
                try:
                    final = evaluate(repo_root, current, code_root, github, EmpryoState(), refresh=True)
                except SafetyError as exc:
                    candidate["eligible"] = False
                    candidate["reasons"] = [str(exc)]
                    continue
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
                    latest_state = EmpryoState()
                    candidate["empryo_threads"] = latest_state.users(Path(candidate["path"]))
                    blockers = latest_state.blockers(Path(candidate["path"]))
                except SafetyError as exc:
                    blockers = [str(exc)]
                if blockers:
                    candidate["eligible"] = False
                    candidate["reasons"] = blockers
                    append_removal(state_root, candidate, "removal_blocked")
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
                    append_removal(state_root, candidate, "removal_blocked")
                    continue
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
            "empryo_threads_scanned": initial_state.thread_count,
            "empryo_unfinished_threads": initial_state.unfinished_count,
            "empryo_pages_scanned": initial_state.page_count,
        }
        summary["per_repo"] = {}
        for row in rows:
            if not row["main_checkout"]:
                counts = summary["per_repo"].setdefault(row["repo"], {"would_remove": 0, "kept_dirty": 0, "kept_unpushed": 0, "in_use": 0})
                counts["would_remove"] += int(row["eligible"])
                counts["kept_dirty"] += int(row["dirty"] is True)
                counts["kept_unpushed"] += int(row["remote_commit_present"] is False)
                counts["in_use"] += int(any(reason in row["reasons"] for reason in ("empryo_thread_unfinished",)))
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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="remove only worktrees that pass every safety check")
    mode.add_argument("--dry-run", action="store_false", dest="apply", help="report counts without removing worktrees")
    parser.set_defaults(apply=False)
    args = parser.parse_args(argv)
    try:
        result = scan(args.code_root.expanduser(), args.state_root.expanduser(), args.apply)
    except SafetyError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
