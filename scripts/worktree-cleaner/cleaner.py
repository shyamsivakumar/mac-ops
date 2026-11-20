#!/usr/bin/env python3

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import datetime as dt
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re

import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from typing import Any

DEFAULT_CODE_ROOT = Path.home() / "Code"
DEFAULT_STATE_ROOT = Path.home() / ".local/state/mac-ops/worktree-cleaner"
T3_WORKTREE_ROOT = Path.home() / ".t3/worktrees"
ARCHIVE_ROOT = Path.home() / ".local/state/archive/worktrees"

SKIP_DIRS = {".git", "node_modules", "vendor", "Pods", ".venv", "venv", "__pycache__", "DerivedData"}
BOOTSTRAP_DIRS = (".specstory/",)
BOOTSTRAP_FILES = {".agents/legacy-instructions.md"}
SHA_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")
# The GitHub call path is the coordinator's, so a commit lookup is counted
# in the same usage log as every other caller's.
_GATEWAY = Path(__file__).resolve().parents[2] / "coordinator" / "bin"
if str(_GATEWAY) not in sys.path:
    sys.path.insert(0, str(_GATEWAY))
import gh_gateway  # noqa: E402
GITHUB_ORIGIN_RE = re.compile(r"^(?:https://(?:[^@/\s]+@)?|ssh://git@|git@)github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?/?$")
WORKERS = 8
COMMIT_CACHE_TTL = 7 * 24 * 3600
# The scan runs its refreshes in threads over one shared cache object. Each
# writer takes this lock around its mutation and save, so two evictions
# cannot race: a later snapshot never drops an earlier eviction.
VERIFIED_LOCK = threading.Lock()


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


def srw_repo(root: Path, repo_slug: str | None = None) -> bool:
    identities = {part.casefold() for part in root.parts} | ({part.casefold() for part in repo_slug.split("/")} if repo_slug else set())
    return "srw" in identities or any(part.startswith("srw-") for part in identities) or any("strategy-replay-workbench" in part for part in identities)


def excluded_repo(root: Path, repo_slug: str | None = None) -> bool:
    parts = {part.casefold() for part in root.parts}
    remote_parts = {part.casefold() for part in repo_slug.split("/")} if repo_slug else set()
    if srw_repo(root, repo_slug):
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


def bootstrap_path(entry: str) -> bool:
    return entry.startswith(BOOTSTRAP_DIRS) or entry in BOOTSTRAP_FILES


def status_for(path: Path) -> tuple[bool, str]:
    records = git_bytes(path, "status", "--porcelain=v1", "--untracked-files=all", "-z").split(b"\0")
    lines = []
    index = 0
    while index < len(records) and records[index]:
        record = os.fsdecode(records[index])
        index += 2 if record[0] in "RC" else 1
        if not (record.startswith("?? ") and bootstrap_path(record[3:])):
            lines.append(record)
    return bool(lines), "\n".join(lines)


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


PROTECTED_REASONS = {"main_checkout", "worktree_outside_scope", "t3_thread_unfinished", "process_cwd_inside", "worktree_locked"}
process_cwd_cache: list[Path] = []


def process_cwds(*, refresh: bool = False) -> list[Path]:
    if refresh or not process_cwd_cache:
        result = run(["lsof", "-d", "cwd", "-Fn"])
        if not result.stdout:
            raise SafetyError("process_cwd_unavailable")
        fresh = [Path(line[1:]) for line in result.stdout.splitlines() if line.startswith("n/")]
        process_cwd_cache[:] = fresh
        return fresh
    return process_cwd_cache


def cwd_held(path: Path) -> bool:
    try:
        return any(inside(holder, path) for holder in process_cwds(refresh=True))
    except SafetyError:
        return True


def branch_exists(repo: Path, branch: str | None) -> bool:
    return bool(branch) and run(["git", "-C", str(repo), "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"]).returncode == 0


def prunable(row: dict[str, Any], github: GitHub) -> bool:
    repo = Path(row["repo"])
    reasons = set(row["reasons"])
    return (
        row["gone"] and not row["locked"] and not row["main_checkout"]
        and not reasons & {"worktree_outside_scope", "t3_thread_unfinished", "repository_outside_code_root", "process_cwd_inside", "worktree_status_unknown"}
        and Path(row["path"]).parent.is_dir()
        and github.repo(repo) is not None
        and (row["remote_commit_present"] is True or branch_exists(repo, row["branch"]))
    )


def created_seconds_ago(path: Path) -> int | None:
    try:
        stat = (path / ".git").stat()
    except OSError:
        return None
    return int(time.time() - getattr(stat, "st_birthtime", stat.st_mtime))


def unpushed_commits(path: Path) -> int | None:
    try:
        return int(git(path, "rev-list", "--count", "HEAD", "--not", "--remotes").strip())
    except (SafetyError, ValueError):
        return None


def categorize(row: dict[str, Any]) -> str:
    if row.get("removed"):
        return "removed"
    if row["eligible"]:
        return "safe"
    reasons = set(row["reasons"])
    if row["prunable"]:
        return "prune"
    if reasons & PROTECTED_REASONS:
        return "protected"
    return "look"


class T3State:
    PAGE_LIMIT = 100
    MAX_PAGES = 1000
    worktree_cache: dict[str, tuple[str, str | None]] = {}

    SNAPSHOT_ATTEMPTS = 5
    SNAPSHOT_PAUSE_SECONDS = 1

    def __init__(self):
        for attempt in range(self.SNAPSHOT_ATTEMPTS):
            try:
                self._read_threads()
                first_safety = self._safety_view()
                first_pages = self.page_count
                self._read_threads()
                if self._safety_view() == first_safety:
                    self.page_count += first_pages
                    return
            except SafetyError as exc:
                if str(exc) != "t3_list_changed":
                    raise
            if attempt + 1 < self.SNAPSHOT_ATTEMPTS:
                time.sleep(self.SNAPSHOT_PAUSE_SECONDS * 2**attempt)
        raise SafetyError("t3_list_changed")

    def _safety_view(self) -> frozenset[tuple[str, str | None]]:
        return frozenset((thread_id, worktree) for thread_id, (_, worktree) in self.records.items())

    @staticmethod
    def _call(tool: str, args: dict[str, Any]) -> Any:
        result = run(["t3mcp", "call", tool, json.dumps(args)])
        if result.returncode != 0:
            raise SafetyError("t3_unavailable")
        try:
            return json.loads(result.stdout)
        except (ValueError, TypeError) as exc:
            raise SafetyError("t3_response_invalid") from exc

    def _read_threads(self) -> None:
        self.records: dict[str, tuple[str, str | None]] = {}
        self.paths: list[tuple[Path, str]] = []
        self.thread_count = 0
        self.page_count = 0
        listed: list[tuple[str, str]] = []
        cursor = 0
        total: int | None = None
        while self.page_count < self.MAX_PAGES:
            page = self._call("t3_thread_list", {"allProjects": True, "settled": False, "limit": self.PAGE_LIMIT, "cursor": cursor})
            rows = page.get("threads") if isinstance(page, dict) else None
            page_total = page.get("total") if isinstance(page, dict) else None
            if not isinstance(rows, list) or len(rows) > self.PAGE_LIMIT or type(page_total) is not int or page_total < 0:
                raise SafetyError("t3_list_invalid")
            if total is not None and page_total != total:
                raise SafetyError("t3_list_changed")
            total = page_total
            self.page_count += 1
            for thread in rows:
                thread_id = thread.get("threadId") if isinstance(thread, dict) else None
                if not isinstance(thread_id, str) or not thread_id or thread_id in {seen for seen, _ in listed}:
                    raise SafetyError("t3_list_duplicate_or_invalid_thread")
                updated_at = thread.get("updatedAt")
                if thread.get("settled") is not False or not isinstance(updated_at, str) or not updated_at:
                    raise SafetyError("t3_thread_invalid")
                listed.append((thread_id, updated_at))
            next_cursor = page.get("nextCursor")
            if next_cursor is None:
                if len(listed) != total:
                    raise SafetyError("t3_list_incomplete")
                break
            if not rows or type(next_cursor) is not int or next_cursor != cursor + len(rows) or len(listed) >= total:
                raise SafetyError("t3_list_incomplete")
            cursor = next_cursor
        else:
            raise SafetyError("t3_list_incomplete")
        for thread_id, updated_at in listed:
            cached = self.worktree_cache.get(thread_id)
            if cached is None or cached[0] != updated_at:
                read = self._call("t3_thread_read", {"threadId": thread_id, "limit": 1})
                thread = read.get("thread") if isinstance(read, dict) else None
                if not isinstance(thread, dict) or thread.get("threadId") != thread_id or "worktreePath" not in thread:
                    raise SafetyError("t3_thread_path_unverified")
                worktree = thread["worktreePath"]
                if worktree is not None and (not isinstance(worktree, str) or not worktree or "\0" in worktree or not Path(worktree).is_absolute()):
                    raise SafetyError("t3_thread_path_invalid")
                cached = self.worktree_cache[thread_id] = (updated_at, worktree and canonical(worktree))
            self.records[thread_id] = cached
            if cached[1]:
                self.paths.append((Path(cached[1]), thread_id))
        self.thread_count = len(listed)

    def users(self, path: Path) -> list[str]:
        return sorted({thread_id for thread_path, thread_id in self.paths if inside(thread_path, path)})

    def blockers(self, path: Path) -> list[str]:
        return ["t3_thread_unfinished"] if self.users(path) else []


class GitHub:
    def __init__(self, cache_path: Path | None = None):
        self.cache_path = cache_path
        self.verified: dict[str, float] = {}
        if cache_path:
            try:
                loaded = json.loads(cache_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                loaded = {}
            if isinstance(loaded, dict):
                self.verified = {key: stamp for key, stamp in loaded.items() if isinstance(stamp, (int, float))}
        self.repos: dict[str, str | None] = {}
        self.commits: dict[tuple[str, str], bool] = {}
        self.pull_requests: dict[tuple[str, str, str], list[dict[str, Any]] | None] = {}

    def repo(self, root: Path, *, refresh: bool = False) -> str | None:
        key = canonical(root)
        if key in self.repos and not refresh:
            return self.repos[key]
        try:
            origin = run(["git", "-C", str(root), "remote", "get-url", "origin"])
        except SafetyError:
            origin = None
        matched = GITHUB_ORIGIN_RE.fullmatch(origin.stdout.strip()) if origin and origin.returncode == 0 else None
        if matched and re.fullmatch(r"[^/\s]+/[^/\s]+", matched.group(1)):
            self.repos[key] = matched.group(1)
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
        cache_key = f"{repo}@{sha.lower()}"
        if not refresh and time.time() - self.verified.get(cache_key, 0) < COMMIT_CACHE_TTL:
            self.commits[key] = True
            return True
        try:
            # Through the metered helper, so a cold scan is visible in the
            # usage log. A forced refresh skips its cache.
            result = gh_gateway.run(
                ["gh", "api", f"repos/{repo}/commits/{sha}", "--jq", ".sha"],
                timeout=30, fresh=refresh, caller_name="worktree-cleaner",
                # An inventory lookup is optional and takes the shared
                # floor. The verification before a removal is required, so
                # it passes none.
                limit=None if refresh else gh_gateway.floor())
            self.commits[key] = result.returncode == 0 and result.stdout.strip().lower() == sha.lower()
        except gh_gateway.ApiBudgetExhausted:
            # The quota is below the floor: the lookup is skipped and the
            # commit stays unverified, which is not a reason to remove.
            self.commits[key] = False
            return False
        except (OSError, subprocess.TimeoutExpired) as exc:
            # The refresh did not answer, so the positive it was checking is
            # no longer known good. Evict it and save before the error goes
            # up, or the next scan reloads it and calls the commit verified.
            self.commits[key] = False
            with VERIFIED_LOCK:
                # One authoritative map: every update happens here under the
                # lock and is written from it, so a later lookup can neither
                # restore an eviction nor drop a fresh verification.
                self.verified.pop(cache_key, None)
                self.save_cache()
            raise SafetyError("command_unavailable:gh") from exc
        except SafetyError:
            self.commits[key] = False
        with VERIFIED_LOCK:
            if self.commits[key]:
                self.verified[cache_key] = time.time()
            else:
                self.verified.pop(cache_key, None)
        return self.commits[key]

    def _load_verified(self) -> dict[str, float]:
        """Read the cache file as it is now, for a locked read-modify-write."""
        if not self.cache_path:
            return dict(self.verified)
        try:
            loaded = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(loaded, dict):
            return {}
        return {key: stamp for key, stamp in loaded.items()
                if isinstance(stamp, (int, float))}

    def save_cache(self) -> None:
        """Write the cache. Callers hold VERIFIED_LOCK around the mutation."""
        if not self.cache_path:
            return
        cutoff = time.time() - COMMIT_CACHE_TTL
        self.verified = {key: stamp for key, stamp in self.verified.items() if stamp > cutoff}
        atomic_write(self.cache_path, json.dumps(self.verified, sort_keys=True))

    def prs(self, repo: str, branch: str, *, refresh: bool = False) -> list[dict[str, Any]] | None:
        owner = repo.split("/", 1)[0]
        key = (repo, owner, branch)
        if key in self.pull_requests and not refresh:
            return self.pull_requests[key]
        try:
            result = run([
                "gh", "pr", "list", "--repo", repo, "--head", branch,
                "--state", "all", "--limit", "1000", "--json", "number,state,headRefName,headRefOid,mergeCommit",
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


def upstream_branch(path: Path, branch: str) -> str | None:
    result = run(["git", "-C", str(path), "config", "--get", f"branch.{branch}.merge"])
    merge_ref = result.stdout.strip().removeprefix("refs/heads/")
    return merge_ref if result.returncode == 0 and merge_ref else None


def merged_contains(path: Path, head: str, pr: dict[str, Any]) -> bool:
    tips = [pr.get("headRefOid"), (pr.get("mergeCommit") or {}).get("oid")]
    return any(tip and run(["git", "-C", str(path), "merge-base", "--is-ancestor", head, tip]).returncode == 0 for tip in tips)


def verify_pr(github: GitHub, repo: str | None, path: Path, branch: str | None, head: str, *, refresh: bool = False) -> tuple[bool, str | None, str | None]:
    if not repo or not branch:
        return False, "github_repository_unknown", None
    names = list(dict.fromkeys([branch, upstream_branch(path, branch) or branch]))
    matching = []
    for name in names:
        prs = github.prs(repo, name, refresh=refresh)
        if prs is None:
            return False, "github_pr_state_unavailable", None
        matching += [row for row in prs if row.get("headRefName") == name]
    if any(str(row.get("state", "")).upper() == "OPEN" for row in matching):
        return False, "github_pr_open", None
    closed = [
        row for row in matching
        if str(row.get("state", "")).upper() == "MERGED" and merged_contains(path, head, row)
        or row.get("headRefName") == branch and str(row.get("state", "")).upper() in {"CLOSED", "MERGED"} and str(row.get("headRefOid", "")).lower() == head.lower()
    ]
    if not closed:
        return False, "github_pr_not_closed_for_head", None
    return True, None, f"https://github.com/{repo}/pull/{closed[-1].get('number')}"


def evaluate(repo_root: Path, record: dict[str, Any], code_root: Path, github: GitHub, t3_state: T3State, *, refresh: bool = False, refresh_cwds: bool = True) -> dict[str, Any]:
    path = Path(record["path"])
    result: dict[str, Any] = {
        "repo": str(repo_root), "path": str(path), "branch": record.get("branch"),
        "head": record.get("head"), "detached": bool(record.get("detached")),
        "main_checkout": canonical(path) == canonical(repo_root), "dirty": None,
        "uncommitted": None, "unpushed": None, "age_seconds": created_seconds_ago(path),
        "gone": not path.is_dir(), "locked": bool(record.get("locked")), "prunable": False,
        "remote_commit_present": None, "pull_request": None, "eligible": False, "reasons": [],
    }
    reasons = t3_state.blockers(path)
    result["t3_threads"] = t3_state.users(path)
    if not inside(repo_root, code_root):
        reasons.append("repository_outside_code_root")
    if result["main_checkout"] or record.get("bare"):
        reasons.append("main_checkout")
    if not any(inside(path, root) for root in (code_root / ".worktrees", repo_root / ".claude/worktrees", T3_WORKTREE_ROOT, Path("/private/tmp"), Path("/tmp"))):
        reasons.append("worktree_outside_scope")
    if any(reason != "t3_thread_unfinished" for reason in reasons):
        result["reasons"] = reasons
        return result
    if any(inside(holder, path) for holder in process_cwds(refresh=refresh and refresh_cwds)):
        reasons.append("process_cwd_inside")
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
            dirty, status = status_for(path)
            result["dirty"] = dirty
            result["uncommitted"] = len(status.splitlines())
            result["unpushed"] = unpushed_commits(path)
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
        ok, why, pr_url = verify_pr(github, repo_slug, path, record.get("branch"), str(record.get("head") or ""), refresh=refresh)
        result["pull_request"] = pr_url
        if not ok and why:
            reasons.append(why)
    result["reasons"] = sorted(set(reasons))
    result["eligible"] = not result["reasons"]
    result["prunable"] = prunable(result, github)
    return result


def excluded_row(repo_root: Path, record: dict[str, Any], reason: str, t3_state: T3State) -> dict[str, Any]:
    path = Path(record["path"])
    row: dict[str, Any] = {
        "repo": str(repo_root), "path": str(path), "branch": record.get("branch"), "reason": reason,
        "gone": not path.is_dir(), "age_seconds": created_seconds_ago(path), "dirty": None,
        "uncommitted": None, "t3_threads": t3_state.users(path),
    }
    if not row["gone"]:
        try:
            row["dirty"], status = status_for(path)
            row["uncommitted"] = len(status.splitlines())
        except SafetyError:
            pass
    return row


def inventory(code_root: Path, github: GitHub, t3_state: T3State) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
    excluded = 0
    process_cwds()
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        excluded_futures = []
        row_futures = []
        for repo_root in discover_repositories(code_root):
            repo_slug = github.repo(repo_root)
            if excluded_repo(repo_root, repo_slug):
                excluded += 1
                reason = "SRW repository" if srw_repo(repo_root, repo_slug) else "Slash dbt or omni repository"
                excluded_futures.extend(pool.submit(excluded_row, repo_root, record, reason, t3_state) for record in worktrees(repo_root) if canonical(record["path"]) != canonical(repo_root))
                continue
            records = worktrees(repo_root)
            for record in records:
                row_futures.append(pool.submit(evaluate, repo_root, record, code_root, github, t3_state))
        rows = [future.result() for future in row_futures]
        excluded_rows = [future.result() for future in excluded_futures]
    return rows, excluded, excluded_rows


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
    lines.extend(["", "## T3-held worktrees", ""])
    for row in rows:
        if row.get("t3_threads"):
            lines.append(f"- `{row['path']}`: {', '.join(row['t3_threads'])}")
    report_dir = code_root / "coordinator" / "evidence"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"worktrees-kept-{day}.md"
    atomic_write(path, "\n".join(lines) + "\n")
    return path


def append_removal(state_root: Path, row: dict[str, Any], event: str, extra: dict[str, Any] | None = None) -> None:
    path = state_root.parent / "worktree-cleaner.log"
    if path.is_symlink():
        raise SafetyError("unsafe_removal_log")
    entry = {
        "event": event,
        "removed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repo": row["repo"], "path": row["path"], "branch": row["branch"],
        "head": row["head"], "pull_request": row["pull_request"],
        "reason": "clean, remote commit verified, no live T3 thread, and closed or merged PR (commits contained) or detached idle for 24 hours",
        **(extra or {}),
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as output:
        output.write(json.dumps(entry, sort_keys=True) + "\n")
        output.flush()
        os.fsync(output.fileno())


@contextlib.contextmanager
def cleaner_lock(state_root: Path):
    lock_path = state_root / "cleaner.lock"
    if lock_path.is_symlink():
        raise SafetyError("unsafe_lock_file")
    with lock_path.open("a+") as lock:
        os.chmod(lock_path, 0o600)
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SafetyError("cleaner_already_running") from exc
        yield


def scan(code_root: Path, state_root: Path, apply: bool, report: bool = True, prune: bool = False) -> dict[str, Any]:
    state_root = secure_state_dir(state_root)
    with cleaner_lock(state_root):
        initial_state = T3State()
        github = GitHub(state_root / "github-commits.json")
        rows, excluded, excluded_rows = inventory(code_root, github, initial_state)
        github.save_cache()
        eligible = [row for row in rows if row["eligible"]]
        removed = 0
        if apply:
            def refreshed(candidate: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | SafetyError | None]:
                repo_root = Path(candidate["repo"])
                current = next((r for r in worktrees(repo_root) if canonical(r["path"]) == canonical(candidate["path"])), None)
                if current is None:
                    return None, None
                try:
                    return current, evaluate(repo_root, current, code_root, github, T3State(), refresh=True)
                except SafetyError as exc:
                    return current, exc

            with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
                checks = list(pool.map(refreshed, eligible))
            for candidate, (current, final) in zip(eligible, checks):
                repo_root = Path(candidate["repo"])
                if current is None:
                    candidate["eligible"] = False
                    candidate["reasons"] = ["worktree_registration_changed"]
                    continue
                if isinstance(final, SafetyError):
                    candidate["eligible"] = False
                    candidate["reasons"] = [str(final)]
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
                    latest_state = T3State()
                    candidate["t3_threads"] = latest_state.users(Path(candidate["path"]))
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
                if cwd_held(Path(candidate["path"])):
                    append_removal(state_root, candidate, "removal_blocked")
                    candidate["eligible"] = False
                    candidate["reasons"] = ["process_cwd_inside"]
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
                run(["git", "-C", str(repo_root), "worktree", "prune"])
                append_removal(state_root, candidate, "removed")
                candidate["eligible"] = False
                candidate["removed"] = True
                removed += 1
        for row in rows:
            row["category"] = categorize(row)
        pruned = 0
        if apply and prune:
            def prune_check(row: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
                repo_root = Path(row["repo"])
                current = next((r for r in worktrees(repo_root) if canonical(r["path"]) == canonical(row["path"])), None)
                if current is None:
                    return None, None
                try:
                    return current, evaluate(repo_root, current, code_root, github, T3State(), refresh=True)
                except SafetyError:
                    return current, None

            prune_rows = [r for r in rows if r["category"] == "prune"]
            with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
                prune_checks = list(pool.map(prune_check, prune_rows))
            for row, (current, final) in zip(prune_rows, prune_checks):
                repo_root = Path(row["repo"])
                if current is None or final is None:
                    continue
                if not final["prunable"] or current.get("head") != row.get("head"):
                    continue
                append_removal(state_root, row, "prune_attempted")
                if run(["git", "-C", str(repo_root), "worktree", "remove", row["path"]]).returncode != 0:
                    append_removal(state_root, row, "prune_failed")
                    continue
                append_removal(state_root, row, "pruned")
                row["category"] = "removed"
                pruned += 1
        # The refresh above reads GitHub again, and a failed refresh evicts
        # the cached verification of that commit. Save once more inside the
        # lock, so a later scan cannot reload a positive the refresh just
        # disproved.
        github.save_cache()
        summary = {
            "mode": "apply" if apply else "dry-run",
            "repositories_scanned": len({row["repo"] for row in rows}),
            "worktrees_scanned": len(rows),
            "eligible": sum(1 for row in rows if row["eligible"]),
            "removed": removed,
            "pruned": pruned,
            "categories": {name: sum(1 for row in rows if row["category"] == name and not row["main_checkout"]) for name in ("safe", "look", "protected", "prune", "removed")},
            "excluded_worktrees": len(excluded_rows),
            "excluded_rows": excluded_rows,
            "held": sum(1 for row in rows if not row["eligible"] and not row.get("removed")),
            "excluded_repositories": excluded,
            "held_reasons": {},
            "t3_threads_scanned": initial_state.thread_count,
            "t3_pages_scanned": initial_state.page_count,
        }
        summary["per_repo"] = {}
        for row in rows:
            if not row["main_checkout"]:
                counts = summary["per_repo"].setdefault(row["repo"], {"would_remove": 0, "kept_dirty": 0, "kept_unpushed": 0, "in_use": 0})
                counts["would_remove"] += int(row["eligible"])
                counts["kept_dirty"] += int(row["dirty"] is True)
                counts["kept_unpushed"] += int(row["remote_commit_present"] is False)
                counts["in_use"] += int(any(reason in row["reasons"] for reason in ("t3_thread_unfinished",)))
            for reason in row.get("reasons", []):
                summary["held_reasons"][reason] = summary["held_reasons"].get(reason, 0) + 1
        if report:
            summary["daily_report"] = str(write_daily_report(code_root, rows, summary, dry_run=not apply))
        summary["rows"] = rows
        return summary


def registrations(code_root: Path, github: GitHub) -> dict[str, tuple[Path, dict[str, Any]]]:
    found: dict[str, tuple[Path, dict[str, Any]]] = {}
    for repo_root in discover_repositories(code_root):
        if excluded_repo(repo_root, github.repo(repo_root)):
            continue
        for record in worktrees(repo_root):
            found.setdefault(canonical(record["path"]), (repo_root, record))
    return found


def pin_head(repo_root: Path, name: str, checkout: Path) -> tuple[str, str]:
    head = git(checkout, "rev-parse", "HEAD").strip()
    ref = f"refs/archive/worktrees/{re.sub(r'[^A-Za-z0-9._-]', '-', name)}-{head[:12]}"
    git(repo_root, "update-ref", ref, head)
    return head, ref


def look_target(code_root: Path, github: GitHub, repo_root: Path, raw: str, refresh_cwds: bool = True) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    current = next((r for r in worktrees(repo_root) if canonical(r["path"]) == canonical(raw)), None)
    if current is None:
        return None, {"path": raw, "repo": str(repo_root), "reasons": ["worktree_not_registered"]}
    path = Path(current["path"])
    row = evaluate(repo_root, current, code_root, github, T3State(), refresh=True, refresh_cwds=refresh_cwds)
    row["category"] = categorize(row)
    refusal = {"path": raw, "repo": str(repo_root), "branch": row["branch"]}
    if row["category"] != "look":
        return None, {**refusal, "reasons": row["reasons"] if row["category"] == "protected" else ["not_needs_a_look"]}
    if row["gone"]:
        return None, {**refusal, "reasons": ["worktree_missing_or_prunable"]}
    if path.is_symlink():
        return None, {**refusal, "reasons": ["worktree_is_symlink"]}
    return row, refusal


def archive_one(code_root: Path, state_root: Path, github: GitHub, repo_root: Path, raw: str, day_dir: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    row, refusal = look_target(code_root, github, repo_root, raw)
    if row is None:
        return None, refusal
    path = Path(row["path"])
    destination = day_dir / repo_root.name / path.name
    if destination.exists() or destination.is_symlink():
        return None, {**refusal, "reasons": ["archive_target_exists"]}
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.stat().st_dev != path.stat().st_dev:
        return None, {**refusal, "reasons": ["archive_on_another_filesystem"]}
    row["head"], ref = pin_head(repo_root, path.name, path)
    row["archive_path"] = str(destination)
    row["archive_ref"] = ref
    details = {
        "reason": "archived from Needs a look, folder moved and commit pinned, nothing deleted",
        "archive_path": row["archive_path"], "archive_ref": ref,
        "uncommitted": row["uncommitted"], "unpushed": row["unpushed"],
    }
    append_removal(state_root, row, "archive_attempted", details)
    try:
        os.rename(path, destination)
    except OSError:
        append_removal(state_root, row, "archive_failed", details)
        return None, {**refusal, "reasons": ["archive_move_failed"]}
    moved_head, moved_ref = pin_head(repo_root, path.name, destination)
    if moved_head != row["head"]:
        row["head"], row["archive_ref"] = moved_head, moved_ref
        details["archive_ref"] = moved_ref
    stale = {canonical(item["path"]) for item in worktrees(repo_root) if item.get("prunable")}
    row["registration_pruned"] = stale == {canonical(path)}
    if row["registration_pruned"]:
        git(repo_root, "worktree", "prune")
    append_removal(state_root, row, "archived", details)
    return row, None


SAVE_LIMIT = 200 * 1024 * 1024
BULK_DIRS = {"node_modules", ".venv", "venv", "build", "dist", ".next", "target", "DerivedData", "__pycache__", "Pods", "vendor", ".git", ".turbo", ".cache", "coverage", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".gradle", ".expo"}
DELETE_REFUSED = {"worktree_status_unknown", "worktree_root_mismatch", "head_unknown"}


def git_bytes(path: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(["git", "-C", str(path), *args], capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SafetyError("git_save_failed") from exc
    if result.returncode != 0:
        raise SafetyError("git_save_failed")
    return result.stdout


def names(listing: bytes) -> list[str]:
    return [os.fsdecode(name) for name in listing.split(b"\0") if name]


def tracked_diff(path: Path, head: str) -> bytes:
    return git_bytes(path, "diff", "--binary", "--no-ext-diff", "--no-textconv", head)


def snapshot(path: Path) -> dict[str, Any]:
    head = git_bytes(path, "rev-parse", "HEAD").decode().strip()
    status = git_bytes(path, "status", "--porcelain=v1", "--untracked-files=all", "-z")
    untracked = names(git_bytes(path, "ls-files", "--others", "--exclude-standard", "-z"))
    ignored = names(git_bytes(path, "ls-files", "--others", "--ignored", "--exclude-standard", "--directory", "-z"))
    kept = [entry for entry in ignored if not BULK_DIRS & set(entry.rstrip("/").split("/"))]
    if any(entry.endswith("/") for entry in untracked) or any(entry.startswith(b"?? ") and entry.endswith(b"/") for entry in status.split(b"\0")):
        raise SafetyError("nested_repository_inside")
    files = saved_files(path, untracked, "untracked") + saved_files(path, kept, "ignored")
    try:
        stats = [(arc, os.lstat(source).st_size, os.lstat(source).st_mtime_ns) for arc, source in files]
    except OSError as exc:
        raise SafetyError("delete_save_unverified") from exc
    return {
        "head": head, "status": status, "untracked": untracked, "ignored": ignored, "kept": kept,
        "files": files, "stats": stats, "diff": hashlib.sha256(tracked_diff(path, head)).digest(),
    }


def saved_files(path: Path, entries: list[str], prefix: str) -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for entry in entries:
        found = path / entry
        if not entry.endswith("/"):
            files.append((f"{prefix}/{entry}", found))
            continue
        if (found / ".git").exists():
            raise SafetyError("nested_repository_inside")
        for root, dirs, leaves in os.walk(found, followlinks=False):
            if ".git" in dirs or ".git" in leaves:
                raise SafetyError("nested_repository_inside")
            files.extend((f"{prefix}/{Path(root, leaf).relative_to(path)}", Path(root, leaf)) for leaf in leaves + [d for d in dirs if Path(root, d).is_symlink()])
    return files


def save_work(repo_root: Path, path: Path, row: dict[str, Any], tar_path: Path, before: dict[str, Any]) -> None:
    if (path / ".gitmodules").exists():
        raise SafetyError("submodules_inside")
    if any(line[:1] in (b"S", b"h") for line in git_bytes(path, "ls-files", "-v", "-z").split(b"\0")):
        raise SafetyError("hidden_tracked_changes")
    untracked, kept, files = before["untracked"], before["kept"], before["files"]
    skipped = [entry for entry in before["ignored"] if entry not in kept]
    sizes = {arc: size for arc, size, _ in before["stats"]}
    if sum(sizes.values()) > SAVE_LIMIT:
        raise SafetyError("save_too_large")
    patch = tracked_diff(path, row["head"])
    manifest = json.dumps({
        "repo": str(repo_root), "path": str(path), "branch": row["branch"], "head": row["head"],
        "archive_ref": row["archive_ref"], "uncommitted": row["uncommitted"], "unpushed": row["unpushed"],
        "untracked_files": untracked, "ignored_saved": kept, "ignored_skipped": skipped,
        "saved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }, sort_keys=True, indent=2).encode()
    partial = tar_path.with_name(tar_path.name + ".tmp")
    partial.unlink(missing_ok=True)
    try:
        with os.fdopen(os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as output:
            with tarfile.open(fileobj=output, mode="w:gz") as tar:
                for name, data in (("changes.patch", patch), ("manifest.json", manifest)):
                    info = tarfile.TarInfo(name)
                    info.size, info.mtime = len(data), int(time.time())
                    tar.addfile(info, io.BytesIO(data))
                for arc, source in files:
                    tar.add(source, arcname=arc, recursive=False)
            output.flush()
            os.fsync(output.fileno())
        with tarfile.open(partial, "r:gz") as tar:
            members = {member.name: member for member in tar.getmembers()}
        if {"changes.patch", "manifest.json", *sizes} - members.keys():
            raise SafetyError("delete_save_unverified")
        if any(members[arc].isreg() and members[arc].size != os.lstat(source).st_size for arc, source in files):
            raise SafetyError("delete_save_unverified")
        os.replace(partial, tar_path)
    except (tarfile.TarError, OSError) as exc:
        raise SafetyError("delete_save_unverified") from exc
    finally:
        partial.unlink(missing_ok=True)


def delete_one(code_root: Path, state_root: Path, github: GitHub, repo_root: Path, raw: str, day_dir: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    row, refusal = look_target(code_root, github, repo_root, raw, refresh_cwds=False)
    if row is None:
        return None, refusal
    path = Path(row["path"])
    if DELETE_REFUSED & set(row["reasons"]) or row["uncommitted"] is None:
        return None, {**refusal, "reasons": ["worktree_status_unknown"]}
    row["head"], ref = pin_head(repo_root, path.name, path)
    tar_path = day_dir / repo_root.name / f"{path.name}-{row['head'][:12]}-{dt.datetime.now().strftime('%H%M%S')}.tar.gz"
    if tar_path.exists() or tar_path.is_symlink():
        return None, {**refusal, "reasons": ["delete_target_exists"]}
    tar_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    row["archive_ref"] = ref
    row["save_path"] = str(tar_path)
    details = {
        "reason": "deleted from Needs a look, commit pinned and uncommitted work saved to a file",
        "save_path": row["save_path"], "archive_ref": ref,
        "uncommitted": row["uncommitted"], "unpushed": row["unpushed"],
    }
    before = snapshot(path)
    if before["head"] != row["head"]:
        return None, {**refusal, "reasons": ["worktree_changed_before_remove"]}
    try:
        save_work(repo_root, path, row, tar_path, before)
        if snapshot(path) != before:
            raise SafetyError("worktree_changed_before_remove")
    except SafetyError as exc:
        tar_path.unlink(missing_ok=True)
        if str(exc) == "worktree_changed_before_remove":
            append_removal(state_root, row, "delete_blocked", details)
        raise
    try:
        append_removal(state_root, row, "delete_attempted", details)
        blockers = T3State().blockers(path)
        if blockers or cwd_held(path) or snapshot(path) != before:
            raise SafetyError(blockers[0] if blockers else "worktree_changed_before_remove")
    except (SafetyError, OSError) as exc:
        tar_path.unlink(missing_ok=True)
        append_removal(state_root, row, "delete_blocked", details)
        return None, {**refusal, "reasons": [str(exc)]}
    try:
        result = run(["git", "-C", str(repo_root), "worktree", "remove", "--force", str(path)], timeout=300)
    except SafetyError:
        append_removal(state_root, row, "delete_outcome_unknown", details)
        return None, {**refusal, "reasons": ["worktree_remove_outcome_unknown"]}
    if result.returncode != 0 or path.exists() or any(canonical(item["path"]) == canonical(path) for item in worktrees(repo_root)):
        append_removal(state_root, row, "delete_failed", details)
        if path.is_dir() and snapshot(path) == before:
            tar_path.unlink(missing_ok=True)
        return None, {**refusal, "reasons": ["delete_remove_failed"]}
    append_removal(state_root, row, "deleted", details)
    return row, None


def archive(code_root: Path, state_root: Path, paths: list[Path], delete: bool = False) -> dict[str, Any]:
    state_root = secure_state_dir(state_root)
    day_dir = ARCHIVE_ROOT / report_day()
    with cleaner_lock(state_root):
        github = GitHub()
        found = registrations(code_root, github)
        one = delete_one if delete else archive_one
        archived: list[dict[str, Any]] = []
        refused: list[dict[str, Any]] = []
        for raw in paths:
            entry = found.get(canonical(raw))
            if entry is None:
                refused.append({"path": os.fspath(raw), "reasons": ["worktree_not_registered"]})
                continue
            try:
                row, refusal = one(code_root, state_root, github, entry[0], os.fspath(raw), day_dir)
            except (SafetyError, OSError) as exc:
                row, refusal = None, {"path": os.fspath(raw), "repo": str(entry[0]), "reasons": [str(exc)]}
            if row:
                archived.append(row)
            if refusal:
                refused.append(refusal)
        return {"mode": "delete" if delete else "archive", "archive_dir": str(day_dir), "deleted" if delete else "archived": archived, "refused": refused}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely review and remove eligible Git worktrees under repositories in ~/Code.")
    parser.add_argument("--code-root", type=Path, default=DEFAULT_CODE_ROOT)
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="remove only worktrees that pass every safety check")
    mode.add_argument("--dry-run", action="store_false", dest="apply", help="report counts without removing worktrees")
    mode.add_argument("--archive", nargs="+", type=Path, metavar="PATH", help="move Needs-a-look worktrees to the archive, pin their commit, keep their branch")
    mode.add_argument("--delete", nargs="+", type=Path, metavar="PATH", help="remove Needs-a-look worktrees, pin their commit, and save uncommitted work to a small file in the archive")
    parser.add_argument("--prune", action="store_true", help="with --apply, also drop registrations whose folder is gone and that pass every prune check")
    parser.add_argument("--no-report", action="store_true", help="skip writing the daily kept-worktrees report")
    parser.set_defaults(apply=False)
    args = parser.parse_args(argv)
    try:
        if args.archive:
            print(json.dumps(archive(args.code_root.expanduser(), args.state_root.expanduser(), args.archive), sort_keys=True))
            return 0
        if args.delete:
            print(json.dumps(archive(args.code_root.expanduser(), args.state_root.expanduser(), args.delete, delete=True), sort_keys=True))
            return 0
        result = scan(args.code_root.expanduser(), args.state_root.expanduser(), args.apply, not args.no_report, args.prune)
    except SafetyError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
