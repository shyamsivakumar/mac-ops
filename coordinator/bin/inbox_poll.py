import json
import os
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
                             "--limit", str(LIMIT), "--json", FIELDS])
    if result.returncode:
        raise RuntimeError(result.stderr)
    prs = json.loads(result.stdout)
    if len(prs) == LIMIT:
        print(f"{repo}: the limit of {LIMIT} open pull requests was reached; any beyond the"
              " newest are not polled this pass, they were seen on an earlier pass",
              file=sys.stderr)
    return prs


def poll_prs(repos, fetch, *, now):
    total = 0
    for repo in repos:
        try:
            prs = fetch(repo)
        except Exception as exc:
            print(f"{repo}: {exc}", file=sys.stderr)
            continue
        for pr in prs:
            try:
                total += _poll_pr(repo, pr, now)
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                print(f"{repo} {pr!r}: {exc}", file=sys.stderr)
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
            rid, state = review.get("id"), review.get("state")
            if not rid or state == "PENDING" or not review.get("submittedAt"):
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
