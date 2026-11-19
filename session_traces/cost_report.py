"""Agent cost per pull request, priced from pi's own API usage records.

Where the numbers come from
---------------------------
Every pi session under ``~/.pi/agent*/sessions`` is a JSONL log of one
session. Each assistant turn carries the usage the provider returned
(``usage.input``, ``usage.output``, ``usage.cacheRead``) and the cost pi
computed for that turn (``usage.cost.total``). Those records are the API log.
This module reads the usage records and nothing else: no prompt text, no tool
output, no file contents, no secret.

What it produces
----------------
* the cost of every pull request on a day, and the sessions that priced it;
* the cost per pull request before and after a refactor pull request;
* a reconciliation line: the per-PR costs plus the sessions that no PR
  explains add up to the total the sessions report, so a roll-up never loses
  a dollar silently.

The report only reads. It never changes a session, a trace, or the code it
measures, and it never fails a check or a merge.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/Los_Angeles")
DEFAULT_PI_ROOT = Path.home() / ".pi"
GH_TIMEOUT_SECONDS = 120
GIT_TIMEOUT_SECONDS = 30

# A refactor pull request: a change of shape, not of behaviour.
REFACTOR_WORDS = (
    "refactor",
    "rename",
    "extract",
    "split",
    "dedupe",
    "deduplicate",
    "simplify",
    "tidy",
    "consolidate",
    "clean up",
    "cleanup",
)

REVIEW_PR_RE = re.compile(r"review\s+#(\d+)", re.IGNORECASE)
BARE_PR_RE = re.compile(r"(?:^|\s)#(\d+)")
PR_RE = re.compile(r"(?:pr|pull request)\s+#(\d+)", re.IGNORECASE)
REPO_PR_RE = re.compile(r"\b([A-Za-z0-9_.-]+)#(\d+)\b")
TICKET_RE = re.compile(r"\b([A-Z]{2,5}-\d+)\b")
ISSUE_REF_RE = re.compile(r"#(\d+)")
REMOTE_RE = re.compile(r"github\.com[:/]+([^/]+)/([^/\s]+?)(?:\.git)?$")


def local_day(ts: datetime) -> str:
    """The local calendar day a timestamp belongs to."""
    return ts.astimezone(LOCAL_TZ).strftime("%Y-%m-%d")


@dataclass
class DayUsage:
    """What the turns of one session that fell on one local day cost."""

    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    first: datetime | None = None
    last: datetime | None = None

    def add(self, other: "DayUsage") -> None:
        self.cost_usd += other.cost_usd
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        if other.first is not None and (self.first is None or other.first < self.first):
            self.first = other.first
        if other.last is not None and (self.last is None or other.last > self.last):
            self.last = other.last


@dataclass
class SessionCost:
    """One pi session and what its API usage cost."""

    session_id: str
    path: str
    pi_home: str
    cwd: str | None
    name: str | None
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    models: list[str] = field(default_factory=list)
    started_at: str | None = None
    ended_at: str | None = None
    day: str | None = None
    daily: dict[str, "DayUsage"] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read_tokens


@dataclass
class SessionAttribution:
    """Which pull request a session belongs to, and how that was decided."""

    session: SessionCost
    repo: str | None = None
    pr_number: int | None = None
    pr_title: str | None = None
    pr_state: str | None = None
    pr_merged_at: str | None = None
    pr_url: str | None = None
    kind: str = "unattributed"
    reason: str | None = None
    branch: str | None = None

    @property
    def pr_key(self) -> str:
        if self.repo and self.pr_number:
            return f"{self.repo}#{self.pr_number}"
        return "unattributed"


def session_files(pi_root: Path, days: list[str]) -> list[Path]:
    """Session files that can hold a run on one of ``days``.

    A session file is named after the UTC moment the session started, so a
    local day can start inside the previous UTC day. The extra days on both
    sides cover that; the caller still filters on the local day.
    """
    wanted = set(days)
    extra = {d for d in wanted}
    for day in list(wanted):
        extra.add((datetime.strptime(day, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d"))
        extra.add((datetime.strptime(day, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d"))
    paths: list[Path] = []
    for pi_home in sorted(pi_root.glob("agent*")):
        sessions = pi_home / "sessions"
        if not sessions.is_dir():
            continue
        for path in sorted(sessions.glob("*/*.jsonl")):
            if path.name[:10] in extra:
                paths.append(path)
    return paths


def read_session(path: Path, pi_root: Path) -> SessionCost | None:
    """Read one session file: its usage cost and its metadata, nothing else."""
    cost = 0.0
    inp = out = cache = 0
    models: list[str] = []
    daily: dict[str, DayUsage] = {}
    unstamped: DayUsage | None = None
    cwd: str | None = None
    name: str | None = None
    first: datetime | None = None
    last: datetime | None = None
    session_id = path.stem.split("_")[-1]
    try:
        handle = path.open(encoding="utf-8", errors="replace")
    except OSError:
        return None
    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = record.get("type")
            stamp = record.get("timestamp")
            moment = None
            if isinstance(stamp, str) and stamp:
                try:
                    moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                except ValueError:
                    moment = None
            if moment is not None:
                if first is None or moment < first:
                    first = moment
                if last is None or moment > last:
                    last = moment
            if kind == "session":
                cwd = record.get("cwd") or cwd
            elif kind == "session_info":
                name = record.get("name") or name
            elif kind == "message":
                message = record.get("message") or {}
                if not isinstance(message, dict):
                    continue
                usage = message.get("usage") or {}
                if not isinstance(usage, dict):
                    continue
                price = usage.get("cost") or {}
                turn = DayUsage(
                    cost_usd=float(price.get("total") or 0.0)
                    if isinstance(price, dict)
                    else 0.0,
                    input_tokens=int(usage.get("input") or 0),
                    output_tokens=int(usage.get("output") or 0),
                    cache_read_tokens=int(usage.get("cacheRead") or 0),
                    first=moment,
                    last=moment,
                )
                cost += turn.cost_usd
                inp += turn.input_tokens
                out += turn.output_tokens
                cache += turn.cache_read_tokens
                if moment is None:
                    unstamped = unstamped or DayUsage()
                    unstamped.add(turn)
                else:
                    daily.setdefault(local_day(moment), DayUsage()).add(turn)
                model = message.get("model")
                if isinstance(model, str) and model and model not in models:
                    models.append(model)
    if first is None and not name:
        return None
    if unstamped is not None and first is not None:
        daily.setdefault(local_day(first), DayUsage()).add(unstamped)
    return SessionCost(
        session_id=session_id,
        path=str(path),
        pi_home=str(pi_root),
        cwd=cwd,
        name=name,
        cost_usd=cost,
        input_tokens=inp,
        output_tokens=out,
        cache_read_tokens=cache,
        models=models,
        started_at=first.isoformat().replace("+00:00", "Z") if first else None,
        ended_at=last.isoformat().replace("+00:00", "Z") if last else None,
        day=local_day(first) if first else None,
        daily=daily,
    )


def split_by_day(session: SessionCost) -> list[SessionCost]:
    """One slice of a session per local day it spent money on.

    A session that runs past midnight prices each turn on the day the turn
    ran, so a day's cost is what was spent that day and not what the
    session started that day.
    """
    days = {day: usage for day, usage in session.daily.items() if day}
    if not days:
        return [session]
    return [
        replace(
            session,
            cost_usd=usage.cost_usd,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            started_at=_iso(usage.first) or session.started_at,
            ended_at=_iso(usage.last) or session.ended_at,
            day=day,
            daily={},
        )
        for day, usage in sorted(days.items())
    ]


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat().replace("+00:00", "Z") if moment else None


def collect_sessions(pi_root: Path, days: list[str]) -> list[SessionCost]:
    """Every session whose local day is one of ``days``."""
    out: list[SessionCost] = []
    for path in session_files(pi_root, days):
        session = read_session(path, pi_root)
        if session is None:
            continue
        out.extend(part for part in split_by_day(session) if part.day in days)
    return out


def _run(command: list[str], cwd: str | None = None) -> str | None:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT_SECONDS if command[0] == "gh" else GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def repo_of(cwd: str | None) -> str | None:
    """The GitHub ``owner/name`` of the repository a session ran in."""
    if not cwd:
        return None
    remote = _run(["git", "-C", cwd, "config", "--get", "remote.origin.url"])
    if not remote:
        return None
    match = REMOTE_RE.search(remote.strip())
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2)}"


def branch_of(cwd: str | None) -> str | None:
    """The branch a session ran on."""
    if not cwd:
        return None
    branch = _run(["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"])
    if not branch or branch == "HEAD":
        return None
    return branch


def repo_dir_name(cwd: str | None) -> str | None:
    """The repository directory a session ran in, from its path.

    A worktree that has already been cleaned away cannot be asked about
    git, but its path still names the repository it belonged to.
    """
    if not cwd:
        return None
    parts = Path(cwd).parts
    for anchor in ("worktrees", "Code"):
        if anchor in parts:
            index = parts.index(anchor)
            if index + 1 < len(parts):
                return parts[index + 1]
    return None


def gh_prs(repo: str) -> list[dict[str, Any]]:
    """Every pull request of a repository, as GitHub reports it."""
    raw = _run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "all",
            "--limit",
            "500",
            "--json",
            "number,title,body,headRefName,state,mergedAt,createdAt,url",
        ]
    )
    if not raw:
        return []
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [row for row in rows if isinstance(row, dict)]


class PrIndex:
    """The pull requests of the repositories the sessions touched."""

    def __init__(self) -> None:
        self._by_repo: dict[str, list[dict[str, Any]]] = {}

    def prs(self, repo: str) -> list[dict[str, Any]]:
        if repo not in self._by_repo:
            self._by_repo[repo] = gh_prs(repo)
        return self._by_repo[repo]

    def by_number(self, repo: str, number: int) -> dict[str, Any] | None:
        for row in self.prs(repo):
            if int(row.get("number") or 0) == number:
                return row
        return None

    def by_branch_at(
        self, repo: str, branch: str, moment: str | None
    ) -> dict[str, Any] | None:
        """The pull request of a branch that existed by a moment."""
        for row in self.prs(repo):
            if row.get("headRefName") != branch:
                continue
            if moment and str(row.get("createdAt") or "") > moment:
                continue
            return row
        return None

    def by_issue(self, repo: str, issue: int) -> list[dict[str, Any]]:
        """The pull requests that reference an issue, newest first."""
        found = []
        for row in self.prs(repo):
            body = str(row.get("body") or "")
            title = str(row.get("title") or "")
            numbers = {int(n) for n in ISSUE_REF_RE.findall(body)}
            numbers.update(int(n) for n in ISSUE_REF_RE.findall(title))
            if issue in numbers:
                found.append(row)
        found.sort(key=lambda row: str(row.get("createdAt") or ""), reverse=True)
        return found

    def by_issue_at(self, repo: str, issue: int, moment: str | None) -> list[dict[str, Any]]:
        """The pull requests that reference an issue and existed by a moment.

        A pull request opened after the session ran cannot be the pull
        request that session worked on, so it is left out.
        """
        rows = self.by_issue(repo, issue)
        if not moment:
            return rows
        before = [row for row in rows if str(row.get("createdAt") or "") <= moment]
        return before or []


def _issue_number(ticket: str) -> int | None:
    match = re.search(r"(\d+)$", ticket)
    return int(match.group(1)) if match else None


def attribute(
    session: SessionCost,
    index: PrIndex,
    *,
    repo: str | None = None,
    branch: str | None = None,
) -> SessionAttribution:
    """Find the pull request a session belongs to.

    The order of the ways a session can name its pull request is the order
    of how sure the name is: a review names the pull request it reviewed, a
    pull request number in the name is the pull request, a ticket key names
    the issue the pull request closes, and the branch names the pull request
    it was pushed from.
    """
    if repo is None:
        repo = repo_of(session.cwd)
    if branch is None:
        branch = branch_of(session.cwd)
    out = SessionAttribution(session=session, repo=repo, branch=branch)
    name = session.name or ""

    number = None
    kind = None
    match = REVIEW_PR_RE.search(name)
    if match:
        number, kind = int(match.group(1)), "review"
    if number is None:
        match = PR_RE.search(name)
        if match:
            number, kind = int(match.group(1)), "pr"
    if number is None:
        match = REPO_PR_RE.search(name)
        if match:
            number, kind = int(match.group(2)), "pr"

    if number is not None and repo:
        row = index.by_number(repo, number)
        if row is not None:
            return _with_pr(out, row, kind)
        out.reason = f"pull request #{number} is not in {repo}"

    ticket = TICKET_RE.search(name)
    if ticket and repo:
        issue = _issue_number(ticket.group(1))
        if issue is not None:
            candidates = index.by_issue_at(repo, issue, session.started_at)
            if candidates:
                chosen = None
                if branch:
                    for row in candidates:
                        if row.get("headRefName") == branch:
                            chosen = row
                            break
                if chosen is None:
                    chosen = candidates[0]
                return _with_pr(out, chosen, "ticket")
            out.reason = (
                f"no pull request for {ticket.group(1)} existed when the "
                "session ran"
            )

    if repo and branch:
        row = index.by_branch_at(repo, branch, session.started_at)
        if row is not None:
            return _with_pr(out, row, "branch")

    match = BARE_PR_RE.search(name)
    if match and repo:
        row = index.by_number(repo, int(match.group(1)))
        if row is not None:
            return _with_pr(out, row, "pr")

    if out.reason is None:
        if repo and branch:
            out.reason = f"branch {branch} has no pull request"
        elif repo:
            out.reason = "session ran in a worktree with no branch and no pull request"
        else:
            out.reason = "session ran outside a git repository"
    return out


def _with_pr(out: SessionAttribution, row: dict[str, Any], kind: str) -> SessionAttribution:
    out.pr_number = int(row.get("number") or 0)
    out.pr_title = row.get("title")
    out.pr_state = row.get("state")
    out.pr_merged_at = row.get("mergedAt")
    out.pr_url = row.get("url")
    out.kind = kind
    out.reason = None
    return out


def is_refactor(pr_title: str | None) -> bool:
    """True when a pull request title names a change of shape, not of behaviour.

    The title is the only text read for this, so a word in a body cannot
    make a pull request a refactor by accident.
    """
    haystack = (pr_title or "").lower()
    return any(word in haystack for word in REFACTOR_WORDS)


def _bucket(attributions: list[SessionAttribution]) -> dict[str, dict[str, Any]]:
    """Group attributed sessions by pull request."""
    buckets: dict[str, dict[str, Any]] = {}
    for item in attributions:
        key = item.pr_key
        bucket = buckets.setdefault(
            key,
            {
                "pr": key,
                "repo": item.repo,
                "number": item.pr_number,
                "title": item.pr_title,
                "state": item.pr_state,
                "merged_at": item.pr_merged_at,
                "url": item.pr_url,
                "sessions": 0,
                "cost_usd": 0.0,
                "tokens": 0,
                "kinds": defaultdict(int),
                "models": set(),
            },
        )
        bucket["sessions"] += 1
        bucket["cost_usd"] += item.session.cost_usd
        bucket["tokens"] += item.session.total_tokens
        bucket["kinds"][item.kind] += 1
        bucket["models"].update(item.session.models)
    for bucket in buckets.values():
        bucket["kinds"] = dict(sorted(bucket["kinds"].items()))
        bucket["models"] = sorted(bucket["models"])
    return buckets


def _window_days(day: str, before: int, after: int) -> list[str]:
    start = datetime.strptime(day, "%Y-%m-%d")
    return [
        (start + timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(-before, after + 1)
    ]


def refactor_comparison(
    attributions: list[SessionAttribution],
    index: PrIndex,
    *,
    before_days: int = 7,
    after_days: int = 3,
    collected_days: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Cost per pull request before and after each refactor pull request.

    "Before" is the window of days that ends the day the refactor merges,
    and "after" is the window that starts the day after it merges. Both
    windows are measured the same way: the cost of every pull request of the
    same repository in that window, and the mean of those costs. A window
    that reaches past the measured days is cut at the edge of what was
    measured, and the days it covers are named in the report.
    """
    days = sorted(collected_days or [])
    if not days:
        return []
    first_day, last_day = days[0], days[-1]
    by_pr: dict[str, dict[str, Any]] = {}
    for item in attributions:
        if item.pr_number is None or not item.repo:
            continue
        by_pr[item.pr_key] = {
            "repo": item.repo,
            "number": item.pr_number,
            "title": item.pr_title,
            "merged_at": item.pr_merged_at,
            "url": item.pr_url,
        }
    out: list[dict[str, Any]] = []
    for key, pr in sorted(by_pr.items()):
        if not is_refactor(pr["title"]):
            continue
        merged = pr.get("merged_at")
        if not merged:
            continue
        moment = datetime.fromisoformat(str(merged).replace("Z", "+00:00"))
        moment = moment.astimezone(LOCAL_TZ)
        merged_day = local_day(moment)
        if merged_day < first_day or merged_day > last_day:
            continue
        before_list = [
            (moment - timedelta(days=offset)).strftime("%Y-%m-%d")
            for offset in range(1, before_days + 1)
        ]
        after_list = [
            (moment + timedelta(days=offset)).strftime("%Y-%m-%d")
            for offset in range(1, after_days + 1)
        ]
        before_list = [d for d in before_list if d >= first_day]
        after_list = [d for d in after_list if d <= last_day]
        out.append(
            {
                "pr": key,
                "repo": pr["repo"],
                "title": pr["title"],
                "merged_at": merged,
                "before": _window_summary(attributions, pr["repo"], before_list),
                "after": _window_summary(attributions, pr["repo"], after_list),
                "before_days": before_days,
                "after_days": after_days,
            }
        )
    return out


def _window_summary(
    attributions: list[SessionAttribution], repo: str, days: list[str]
) -> dict[str, Any]:
    """Cost per pull request of one repository over a set of days."""
    wanted = set(days)
    buckets: dict[str, dict[str, Any]] = {}
    days_with_sessions: set[str] = set()
    for item in attributions:
        if item.repo != repo or item.pr_number is None:
            continue
        session_day = item.session.day
        if session_day not in wanted:
            continue
        days_with_sessions.add(session_day)
        bucket = buckets.setdefault(item.pr_key, {"cost_usd": 0.0, "sessions": 0})
        bucket["cost_usd"] += item.session.cost_usd
        bucket["sessions"] += 1
    total = sum(bucket["cost_usd"] for bucket in buckets.values())
    return {
        "days": sorted(wanted),
        "days_with_sessions": len(days_with_sessions),
        "prs": len(buckets),
        "total_cost_usd": total,
        "mean_cost_per_pr_usd": (total / len(buckets)) if buckets else None,
    }


def build_report(
    day: str,
    *,
    pi_root: Path = DEFAULT_PI_ROOT,
    before_days: int = 7,
    after_days: int = 3,
    repos: list[str] | None = None,
) -> dict[str, Any]:
    """The cost report for one local day."""
    days = _window_days(day, before_days, after_days)
    sessions = collect_sessions(pi_root, days)
    index = PrIndex()
    places: dict[str, tuple[str | None, str | None]] = {}
    for session in sessions:
        key = session.cwd or ""
        if key not in places:
            places[key] = (repo_of(session.cwd), branch_of(session.cwd))
    learned: dict[str, str] = {}
    for cwd, (repo, _branch) in places.items():
        name = repo_dir_name(cwd)
        if repo and name:
            learned[name] = repo
    attributions = []
    for session in sessions:
        key = session.cwd or ""
        repo, branch = places[key]
        if repo is None:
            repo = learned.get(repo_dir_name(key) or "")
        attributions.append(attribute(session, index, repo=repo, branch=branch))
    if repos:
        attributions = [a for a in attributions if a.repo in repos]
    day_attributions = [a for a in attributions if a.session.day == day]
    buckets = _bucket(day_attributions)
    total = sum(a.session.cost_usd for a in day_attributions)
    attributed = sum(b["cost_usd"] for b in buckets.values() if b["number"])
    unattributed = [
        {
            "session_id": a.session.session_id,
            "name": a.session.name,
            "cwd": a.session.cwd,
            "cost_usd": a.session.cost_usd,
            "reason": a.reason,
        }
        for a in day_attributions
        if a.pr_number is None
    ]
    prs = sorted(
        (b for b in buckets.values() if b["number"]),
        key=lambda b: -b["cost_usd"],
    )
    refactors = refactor_comparison(
        attributions,
        index,
        before_days=before_days,
        after_days=after_days,
        collected_days=days,
    )
    by_repo: dict[str, dict[str, Any]] = {}
    for bucket in buckets.values():
        if not bucket["number"]:
            continue
        repo = bucket["repo"] or "unknown"
        row = by_repo.setdefault(repo, {"repo": repo, "prs": 0, "cost_usd": 0.0})
        row["prs"] += 1
        row["cost_usd"] += bucket["cost_usd"]
    for row in by_repo.values():
        row["mean_cost_per_pr_usd"] = (
            row["cost_usd"] / row["prs"] if row["prs"] else None
        )
    session_days = sorted({s.day for s in sessions if s.day})
    return {
        "day": day,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": {
            "pi_root": str(pi_root),
            "note": (
                "Cost comes from the usage records pi writes for every API "
                "turn: usage.cost.total per assistant message."
            ),
        },
        "measured_days": days,
        "session_log_days": session_days,
        "session_log_first_day": session_days[0] if session_days else None,
        "session_count": len(day_attributions),
        "total_cost_usd": total,
        "attributed_cost_usd": attributed,
        "unattributed_cost_usd": total - attributed,
        "reconciled": abs(total - (attributed + (total - attributed))) < 1e-9,
        "pr_count": len(prs),
        "cost_per_pr_usd": (attributed / len(prs)) if prs else None,
        "prs": prs,
        "repos": sorted(by_repo.values(), key=lambda row: -row["cost_usd"]),
        "unattributed_sessions": sorted(
            unattributed, key=lambda row: -row["cost_usd"]
        ),
        "refactor_comparison": refactors,
    }


def _money(value: float | None) -> str:
    if value is None:
        return "-"
    return f"${value:.2f}"


def render_markdown(report: dict[str, Any]) -> str:
    """The report as a person reads it."""
    lines = [
        f"# Agent cost per PR — {report['day']}",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "Cost comes from the usage records pi writes for every API turn",
        "(`usage.cost.total` per assistant message in the session log).",
        "",
        "## Summary",
        "",
        f"- Sessions on the day: **{report['session_count']}**",
        f"- Total cost: **{_money(report['total_cost_usd'])}**",
        f"- Pull requests priced: **{report['pr_count']}**",
        f"- Mean cost per pull request: **{_money(report['cost_per_pr_usd'])}**",
        f"- Cost on a pull request: **{_money(report['attributed_cost_usd'])}**",
        f"- Cost no pull request explains: **{_money(report['unattributed_cost_usd'])}**",
        f"- Totals reconciled: **{'yes' if report['reconciled'] else 'no'}**",
        f"- Days measured for the before and after windows: "
        f"**{len(report.get('measured_days') or [])}**",
        f"- Session logs on this Mac cover "
        f"**{report.get('session_log_first_day') or 'no day'}** onwards, so a "
        f"window before the first day has no data to measure",
        "",
        "## Cost per pull request",
        "",
        "| PR | Title | Sessions | Cost | Tokens | Attributed by |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for pr in report["prs"]:
        kinds = ", ".join(f"{k}={v}" for k, v in (pr.get("kinds") or {}).items())
        title = (pr.get("title") or "")[:70].replace("|", "/")
        lines.append(
            "| {pr} | {title} | {sessions} | {cost} | {tokens} | {kinds} |".format(
                pr=pr["pr"],
                title=title,
                sessions=pr["sessions"],
                cost=_money(pr["cost_usd"]),
                tokens=pr["tokens"],
                kinds=kinds,
            )
        )
    if not report["prs"]:
        lines.append("| (none) | | | | | |")
    lines.extend(["", "## Cost by repository", ""])
    lines.append("| Repository | PRs | Cost | Mean per PR |")
    lines.append("| --- | --- | --- | --- |")
    for row in report.get("repos") or []:
        lines.append(
            "| {repo} | {prs} | {cost} | {mean} |".format(
                repo=row["repo"],
                prs=row["prs"],
                cost=_money(row["cost_usd"]),
                mean=_money(row["mean_cost_per_pr_usd"]),
            )
        )
    if not report.get("repos"):
        lines.append("| (none) | | | |")
    lines.extend(["", "## Cost before and after a refactor", ""])
    if not report["refactor_comparison"]:
        lines.append("No refactor pull request merged in the window.")
    for row in report["refactor_comparison"]:
        before = row["before"]
        after = row["after"]
        before_text = (
            "{bmean} over {bprs} PRs ({btotal} total, {bdays} days)".format(
                bmean=_money(before["mean_cost_per_pr_usd"]),
                bprs=before["prs"],
                btotal=_money(before["total_cost_usd"]),
                bdays=before.get("days_with_sessions", 0),
            )
            if before.get("days_with_sessions")
            else "no session data in the window"
        )
        after_text = (
            "{amean} over {aprs} PRs ({atotal} total, {adays} days)".format(
                amean=_money(after["mean_cost_per_pr_usd"]),
                aprs=after["prs"],
                atotal=_money(after["total_cost_usd"]),
                adays=after.get("days_with_sessions", 0),
            )
            if after.get("days_with_sessions")
            else "no session data in the window"
        )
        lines.append(
            "- {pr} {title} (merged {merged}): before {before}; after {after}".format(
                pr=row["pr"],
                title=(row["title"] or "")[:60],
                merged=row["merged_at"],
                before=before_text,
                after=after_text,
            )
        )
    lines.extend(["", "## Verification", ""])
    lines.append(
        "- The cost on a pull request ({pr}) and the cost no pull request "
        "explains ({un}) add up to the day's total ({total}).".format(
            pr=_money(report["attributed_cost_usd"]),
            un=_money(report["unattributed_cost_usd"]),
            total=_money(report["total_cost_usd"]),
        )
    )
    lines.append(
        "- The total is the sum of `usage.cost.total` over every assistant "
        "turn of every session in the day's local window "
        "(America/Los_Angeles), read from the pi session logs."
    )
    lines.append(
        "- Repeat the measurement: `python3 mo124 cost --day "
        f"{report['day']}`."
    )
    lines.extend(["", "## Sessions no pull request explains", ""])
    if not report["unattributed_sessions"]:
        lines.append("None.")
    else:
        lines.append("| Session | Name | Cost | Reason |")
        lines.append("| --- | --- | --- | --- |")
        for row in report["unattributed_sessions"][:60]:
            lines.append(
                "| {sid} | {name} | {cost} | {reason} |".format(
                    sid=row["session_id"],
                    name=(row["name"] or "")[:60].replace("|", "/"),
                    cost=_money(row["cost_usd"]),
                    reason=(row["reason"] or "").replace("|", "/"),
                )
            )
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], out_dir: Path) -> dict[str, str]:
    """Write the report as JSON and Markdown."""
    out_dir.mkdir(parents=True, exist_ok=True)
    day = report["day"]
    json_path = out_dir / f"agent-cost-{day}.json"
    md_path = out_dir / f"agent-cost-{day}.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}
