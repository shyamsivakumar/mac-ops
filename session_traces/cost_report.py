"""Agent cost per pull request for one local day, priced from pi session usage.

Each assistant turn carries ``usage.cost.total``. A turn is billed to the pull
request named by the latest ``session_info`` name recorded before that turn, and
belongs to the local day of its own timestamp. Report only: it reads usage
numbers and never keeps message content.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/Los_Angeles")
DEFAULT_PI_ROOT = Path.home() / ".pi"
PR_RE = re.compile(r"(?:([\w.-]+/[\w.-]+))?#(\d+)\b")
REMOTE_RE = re.compile(r"github\.com[:/]+([^/]+)/([^/\s]+?)(?:\.git)?$")
UNKNOWN_REPO = "unknown-repo"


def repo_of(cwd: str | None, cache: dict[str, str]) -> str:
    if cwd not in cache:
        remote = subprocess.run(
            ["git", "-C", cwd or "/nonexistent", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        match = REMOTE_RE.search(remote)
        cache[cwd] = f"{match.group(1)}/{match.group(2)}" if match else UNKNOWN_REPO
    return cache[cwd]


def pull_request(name: str | None, cwd: str | None, cache: dict[str, str]) -> str | None:
    named = PR_RE.search(name or "")
    if not named:
        return None
    return f"{named.group(1) or repo_of(cwd, cache)}#{named.group(2)}"


def build_report(day: str, pi_root: Path = DEFAULT_PI_ROOT, repo: str | None = None) -> dict:
    start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=LOCAL_TZ)
    end = start + timedelta(days=1)
    cost: dict[str, float] = defaultdict(float)
    turns: dict[str, int] = defaultdict(int)
    unattributed = 0.0
    repos: dict[str, str] = {}
    for path in sorted(pi_root.glob("agent*/sessions/**/*.jsonl")):
        if path.stat().st_mtime < start.timestamp() or path.name[:10] > end.strftime("%Y-%m-%d"):
            continue
        cwd = name = None
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                record = json.loads(line)
                kind = record.get("type")
                if kind == "session":
                    cwd = record.get("cwd")
                elif kind == "session_info":
                    name = record.get("name")
                elif kind == "message":
                    turn_cost = ((record["message"].get("usage") or {}).get("cost") or {}).get("total")
                    moment = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
                    if not turn_cost or not start <= moment < end:
                        continue
                    key = pull_request(name, cwd, repos)
                    if key is None:
                        unattributed += turn_cost
                    else:
                        cost[key] += turn_cost
                        turns[key] += 1
    if repo:
        cost = {key: value for key, value in cost.items() if key.rpartition("#")[0] == repo}
        unattributed = 0.0
    return {"day": day, "repo": repo, "cost": dict(cost), "turns": dict(turns), "unattributed": unattributed}


def render(report: dict) -> str:
    cost = report["cost"]
    scope = f" in {report['repo']}" if report["repo"] else ""
    lines = [
        f"# Agent cost per pull request{scope}, {report['day']}",
        "",
        f"${sum(cost.values()):.2f} on {len(cost)} pull requests.",
    ]
    if not report["repo"]:
        lines.append(f"${report['unattributed']:.2f} on turns whose session name has no pull request number.")
    lines += ["", "| Pull request | Cost | Turns |", "| --- | ---: | ---: |"]
    lines += [
        f"| {key} | ${value:.2f} | {report['turns'][key]} |"
        for key, value in sorted(cost.items(), key=lambda item: -item[1])
    ]
    return "\n".join(lines) + "\n"
