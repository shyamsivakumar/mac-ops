import fcntl
import math
import os
import re
import sys

import inbox
import inbox_outbox as outbox
import inbox_replay
import journal

SESSION = "coordinator"
MAX_BODY = 4000
SEND = re.compile(r"^SEND\s+([^:\s]+):\s*(\S.*)$")
NOTHING = re.compile(r"^NOTHING:\s*(\S.*)$")
ZEROS = {"batches": 0, "lines": 0}


class ModelUnavailable(Exception):
    pass


def _seconds(name, default):
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        value = None
    if value is None or not math.isfinite(value) or value < 0:
        print(f"{name}={raw!r} is not a usable number; using {default}", file=sys.stderr)
        return default
    return value


def coalesce(rows):
    groups = {}
    for row in rows:
        pr = row["pr"]
        key = (row["repo"], pr, row["kind"]) if pr is not None else (
            row["repo"], pr, row["kind"], row["dedupe_key"])
        group = groups.setdefault(key, {"kind": row["kind"], "repo": row["repo"], "pr": pr, "ids": []})
        group.update(head=row["head"], payload=row["payload"])
        group["ids"].append(row["id"])
    return list(groups.values())


def parse_reply(text):
    if not isinstance(text, str):
        return []
    decisions = []
    for line in text.encode("utf-8", "replace").decode().splitlines():
        send, nothing = SEND.match(line), NOTHING.match(line)
        if send:
            decisions.append(("hc_send", send.group(1), send.group(2)[:MAX_BODY]))
        elif nothing:
            decisions.append(("none", None, nothing.group(1)[:MAX_BODY]))
        elif line.startswith(("SEND", "NOTHING")):
            return []
    return decisions


def finish(rows, reply, *, now):
    decisions = parse_reply(reply)
    if not decisions:
        inbox.release(rows, count_attempt=True)
        return 0
    token = rows[0]["run_id"]
    with inbox.txn() as conn:
        acked = inbox._ack(conn, rows, now)
        if not acked:
            return 0
        for index, (kind, target, body) in enumerate(decisions):
            outbox._insert(conn, token, index, kind, target, "" if kind == "none" else body,
                           body if kind == "none" else None, now)
    return acked


def shadow_runner(lines):
    return "NOTHING: shadow"


def _due(now):
    with inbox.txn() as conn:
        last = inbox._last_run(conn)
        oldest = conn.execute(
            "SELECT MIN(ts) FROM inbox WHERE status='pending' AND session=? AND tier='wake'",
            (SESSION,),
        ).fetchone()[0]
    if oldest is None:
        return False, None
    debounce, gap = _seconds("COORD_INBOX_DEBOUNCE", 60), _seconds("COORD_INBOX_MIN_GAP", 1800)
    due = now - oldest >= debounce and (last is None or now - last >= gap)
    return due, oldest


def shadow_pass(*, now, runner=shadow_runner):
    lock_path = os.path.join(os.path.dirname(inbox._db_path()), "inbox.worker.lock")
    with open(lock_path, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return dict(ZEROS)
        inbox_replay.activate(now=now)
        inbox.reap(now=now)
        inbox.enqueue_due_timers(now=now)
        inbox_replay.replay()
        import inbox_poll
        repos = inbox_poll.configured_repos()
        if repos:
            inbox_poll.poll_prs(repos, inbox_poll.fetch, now=now)
            inbox_poll.poll_ci(repos, inbox_poll.fetch_status, now=now)
        due, oldest = _due(now)
        if not due:
            return dict(ZEROS)
        rows = inbox.claim(SESSION, worker=f"shadow-{os.getpid()}", now=now, pid=os.getpid())
        if not rows:
            return dict(ZEROS)
        lines = coalesce(rows)
        try:
            reply = runner(lines)
        except ModelUnavailable:
            inbox.release(rows, count_attempt=False)
            inbox.set_last_run(now=now)
            return dict(ZEROS)
        except Exception as exc:
            inbox.release(rows, count_attempt=True)
            journal.emit("inbox_run_failed", "inbox_worker", reason=type(exc).__name__,
                         rows=len(rows))
            inbox.set_last_run(now=now)
            return dict(ZEROS)
        acked = finish(rows, reply, now=now)
        inbox.set_last_run(now=now)
        if acked:
            journal.emit("inbox_would_wake", "inbox_worker", rows=len(rows), lines=len(lines),
                         delay=now - oldest)
            return {"batches": 1, "lines": len(lines)}
        journal.emit("inbox_run_failed", "inbox_worker", reason="no decision or lost claim", rows=len(rows))
        return dict(ZEROS)
