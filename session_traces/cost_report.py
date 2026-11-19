"""Agent cost per pull request for one local day, priced from pi session usage.

Each assistant turn in a pi session log (``~/.pi/agent*/sessions``) carries
``usage.cost.total``. The report sums those per turn on the local day the turn
ran, attributes each session to a pull request, and lists the sessions no pull
request explains, so the rows add up to the day's total. Report only: it reads
usage records and changes nothing.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/Los_Angeles")
DEFAULT_PI_ROOT = Path.home() / ".pi"
NAMED_PR_RE = re.compile(r"(?:([A-Za-z0-9_.-]+))?#(\d+)\b")
REMOTE_RE = re.compile(r"github\.com[:/]+([^/]+)/([^/\s]+?)(?:\.git)?$")


def instant(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def read_session(path: Path, day: str) -> dict | None:
    """One session's cost on ``day`` (turns are kept by their own local day)."""
    cwd = name = first = None
    cost = 0.0
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = record.get("type")
            if kind == "session":
                cwd = record.get("cwd")
            elif kind == "session_info":
                name = record.get("name") or name
            elif kind == "message":
                usage = (record.get("message") or {}).get("usage") or {}
                moment = instant(record.get("timestamp"))
                if moment and moment.astimezone(LOCAL_TZ).strftime("%Y-%m-%d") == day:
                    cost += float((usage.get("cost") or {}).get("total") or 0.0)
                    first = first or moment
    if first is None:
        return None
    return {
        "id": path.stem.split("_")[-1],
        "name": name,
        "cwd": cwd,
        "cost": cost,
        "at": first,
    }


def read_sessions(pi_root: Path, day: str) -> list[dict]:
    """Every session file that started by the end of ``day``; a session can stay open for days."""
    upper = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    sessions = []
    for path in sorted(pi_root.glob("agent*/sessions/*/*.jsonl")):
        if path.name[:10] <= upper and (session := read_session(path, day)):
            sessions.append(session)
    return sessions


def run(command: list[str]) -> str | None:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=120, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def repo_of(cwd: str | None) -> str | None:
    remote = (
        run(["git", "-C", cwd, "config", "--get", "remote.origin.url"]) if cwd else None
    )
    match = REMOTE_RE.search(remote or "")
    return f"{match.group(1)}/{match.group(2)}" if match else None


def branch_of(cwd: str | None) -> str | None:
    branch = (
        run(["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"]) if cwd else None
    )
    return None if branch in (None, "HEAD", "main", "master") else branch


class PullRequests:
    """The pull requests of each repository, fetched once."""

    def __init__(self) -> None:
        self.by_repo: dict[str, list[dict]] = {}

    def of(self, repo: str) -> list[dict]:
        if repo not in self.by_repo:
            fields = "number,title,headRefName,createdAt,url"
            raw = run(
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
                    fields,
                ]
            )
            self.by_repo[repo] = json.loads(raw) if raw else []
        return self.by_repo[repo]

    def find(
        self,
        repo: str,
        session: dict,
        *,
        number: int | None = None,
        branch: str | None = None,
    ) -> dict | None:
        """A pull request that existed when the session ran; instants, not text, are compared."""
        for pr in self.of(repo):
            matches = pr["number"] == number if number else pr["headRefName"] == branch
            created = instant(pr["createdAt"])
            if matches and created and created <= session["at"]:
                return pr
        return None


def attribute(session: dict, prs: PullRequests) -> tuple[str, dict] | str:
    """``(repo, pull request)`` for the session, or the reason none explains it."""
    repo = repo_of(session["cwd"])
    named = NAMED_PR_RE.search(session["name"] or "")
    if named:
        owner = repo.split("/")[0] if repo else None
        label = (named.group(1) or "").lower()
        target = (
            f"{owner}/{named.group(1)}"
            if owner and label not in ("", "pr", "review")
            else repo
        )
        if not target:
            return "the session name has a number but no repository to look it up in"
        pr = prs.find(target, session, number=int(named.group(2)))
        return (
            (target, pr)
            if pr
            else f"no pull request {target}#{named.group(2)} existed then"
        )
    branch = branch_of(session["cwd"])
    if repo and branch and (pr := prs.find(repo, session, branch=branch)):
        return repo, pr
    return "no pull request number in the name, and its branch has no pull request"


def build_report(day: str, pi_root: Path = DEFAULT_PI_ROOT) -> dict:
    sessions = read_sessions(pi_root, day)
    prs = PullRequests()
    priced: dict[str, dict] = {}
    unattributed = []
    for session in sessions:
        found = attribute(session, prs)
        if isinstance(found, str):
            unattributed.append(
                {
                    "session": session["id"],
                    "name": session["name"],
                    "cost": session["cost"],
                    "reason": found,
                }
            )
            continue
        repo, pr = found
        row = priced.setdefault(
            f"{repo}#{pr['number']}",
            {"title": pr["title"], "url": pr["url"], "cost": 0.0, "sessions": 0},
        )
        row["cost"] += session["cost"]
        row["sessions"] += 1
    total = sum(session["cost"] for session in sessions)
    rows = sum(row["cost"] for row in priced.values()) + sum(
        row["cost"] for row in unattributed
    )
    return {
        "day": day,
        "sessions": len(sessions),
        "total": total,
        "pull_requests": priced,
        "unattributed": unattributed,
        "reconciled": abs(total - rows) < 1e-6,
    }


def render(report: dict) -> str:
    priced = report["pull_requests"]
    on_prs = sum(row["cost"] for row in priced.values())
    lines = [
        f"# Agent cost per pull request, {report['day']}",
        "",
        f"{report['sessions']} sessions, ${report['total']:.2f} in total. "
        f"${on_prs:.2f} on {len(priced)} pull requests, "
        f"${report['total'] - on_prs:.2f} on {len(report['unattributed'])} sessions no pull request explains. "
        f"Rows add up to the total: {'yes' if report['reconciled'] else 'NO'}.",
        "",
        "| Pull request | Cost | Sessions | Title |",
        "| --- | ---: | ---: | --- |",
    ]
    for key, row in sorted(priced.items(), key=lambda item: -item[1]["cost"]):
        lines.append(
            f"| [{key}]({row['url']}) | ${row['cost']:.2f} | {row['sessions']} | {row['title']} |"
        )
    reasons: dict[str, float] = defaultdict(float)
    for row in report["unattributed"]:
        reasons[row["reason"]] += row["cost"]
    lines += ["", "| Unattributed reason | Cost |", "| --- | ---: |"]
    lines += [
        f"| {reason} | ${cost:.2f} |"
        for reason, cost in sorted(reasons.items(), key=lambda item: -item[1])
    ]
    return "\n".join(lines) + "\n"
