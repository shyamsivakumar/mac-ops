import json
import os
import subprocess
import sys
from datetime import datetime

import gh_gateway
import inbox

LIMIT = 100
FIELDS = "number,headRefOid,isDraft,createdAt,labels,reviews"
HUMAN_LABEL = "merge:human-ok"


def configured_repos():
    return [repo.strip() for repo in (os.environ.get("COORD_INBOX_REPOS") or "").split(",")
            if repo.strip()]


def fetch(repo):
    result = gh_gateway.run(["gh", "pr", "list", "-R", repo, "--state", "open",
                             "--limit", str(LIMIT), "--json", FIELDS],
                            timeout=120, limit=gh_gateway.floor(), caller_name="inbox_poll")
    if result.returncode:
        raise RuntimeError(f"gh pr list exit {result.returncode}")
    prs = json.loads(result.stdout)
    if isinstance(prs, list) and len(prs) == LIMIT:
        print(f"{repo}: {LIMIT} open pull requests returned; any beyond the newest {LIMIT}"
              " are not polled this pass", file=sys.stderr)
    return prs


def _int(value):
    return isinstance(value, int) and not isinstance(value, bool) and abs(value) < 2 ** 63


def _valid(pr):
    return (isinstance(pr, dict) and _int(pr.get("number")) and isinstance(pr.get("headRefOid"), str)
            and isinstance(pr.get("createdAt"), str))


def poll_prs(repos, fetch, *, now):
    total = 0
    for repo in repos:
        try:
            prs = fetch(repo)
        except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
            print(f"{repo}: fetch failed: {type(exc).__name__}", file=sys.stderr)
            continue
        if not isinstance(prs, list):
            print(f"{repo}: fetch returned {type(prs).__name__}, not a list", file=sys.stderr)
            continue
        for pr in prs:
            if not _valid(pr):
                print(f"{repo}: skipped a malformed pull request", file=sys.stderr)
                continue
            try:
                total += _poll_pr(repo, pr, now)
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                print(f"{repo}#{pr['number']}: skipped: {type(exc).__name__}", file=sys.stderr)
    return total


CI_CONTEXTS = "srw/agent-check"


def ci_contexts():
    raw = os.environ.get("COORD_INBOX_CI_CONTEXTS") or CI_CONTEXTS
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def fetch_status(repo):
    result = gh_gateway.run(["gh", "api", f"repos/{repo}/commits/HEAD/status"],
                            timeout=120, limit=gh_gateway.floor(), caller_name="inbox_poll")
    if result.returncode:
        raise RuntimeError(f"gh api exit {result.returncode}")
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        return data
    return {"sha": data.get("sha"), "statuses": data.get("statuses")}


def poll_ci(repos, fetch_status, *, now):
    total = 0
    for repo in repos:
        try:
            data = fetch_status(repo)
        except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
            print(f"{repo}: fetch failed: {type(exc).__name__}", file=sys.stderr)
            continue
        if not isinstance(data, dict):
            print(f"{repo}: fetch returned {type(data).__name__}, not a dict", file=sys.stderr)
            continue
        sha, statuses = data.get("sha"), data.get("statuses")
        if not isinstance(sha, str) or not isinstance(statuses, list):
            print(f"{repo}: skipped a malformed status reply", file=sys.stderr)
            continue
        contexts = ci_contexts()
        found = False
        with inbox.txn() as conn:
            for status in statuses:
                if not isinstance(status, dict):
                    continue
                context, state = status.get("context"), status.get("state")
                if not isinstance(context, str) or context not in contexts:
                    continue
                found = True
                if state not in ("failure", "error", "success"):
                    continue
                total += inbox._insert(conn, "ci_main", f"ci_main:{repo}:{sha}:{context}:{state}",
                                       source="poll", ts=now, repo=repo, head=sha,
                                       payload={"context": context, "state": state},
                                       tier="wake" if state in ("failure", "error") else "batch")
        if not found:
            print(f"{repo}: no Mac-published status", file=sys.stderr)
    return total


def _mark(conn, key, ts):
    conn.execute("INSERT OR IGNORE INTO seen(key, ts) VALUES (?,?)", (key, ts))


def _epoch(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()


def _poll_pr(repo, pr, now):
    number, head = pr["number"], pr["headRefOid"]
    created = _epoch(pr["createdAt"])
    count = 0
    with inbox.txn() as conn:
        stored = conn.execute("SELECT v FROM meta WHERE k=?", ("activated_at",)).fetchone()
        activated = None if stored is None else float(stored["v"])
        opened = f"pr_opened:{repo}#{number}:"
        new_head = f"pr_new_head:{repo}#{number}:{head}"
        first = conn.execute("SELECT 1 FROM seen WHERE key=?", (opened,)).fetchone() is None
        old = activated is not None and created < activated

        def row(kind, key, ts, payload=None):
            return inbox._insert(conn, kind, key, source="poll", ts=ts, repo=repo, pr=number,
                                 head=head, payload=payload)

        if not first:
            count += row("pr_new_head", new_head, now)
        elif old:
            _mark(conn, opened, created)
        else:
            count += row("pr_opened", opened, created, {"draft": bool(pr.get("isDraft"))})
        if first:
            _mark(conn, new_head, now)
        if HUMAN_LABEL in {label["name"] for label in pr.get("labels") or []}:
            signal = f"human_signal:{repo}#{number}:{HUMAN_LABEL}"
            if first and old:
                _mark(conn, signal, created)
            else:
                count += row("human_signal", signal, now,
                             {"verified": False, "label": HUMAN_LABEL})
        for review in pr.get("reviews") or []:
            if not isinstance(review, dict):
                continue
            rid, state = review.get("id"), review.get("state")
            if not isinstance(rid, str) or not rid or state == "PENDING" \
                    or not isinstance(review.get("submittedAt"), str):
                continue
            reviewed = _epoch(review["submittedAt"])
            keys = (f"pr_review:{repo}#{number}:{rid}", f"human_signal:{repo}#{number}:{rid}")
            if activated is not None and reviewed < activated:
                _mark(conn, keys[0], reviewed)
                _mark(conn, keys[1], reviewed)
                continue
            count += row("pr_review", keys[0], reviewed, {"review": rid, "state": state})
            count += row("human_signal", keys[1], reviewed, {"verified": False, "review": rid})
    return count
