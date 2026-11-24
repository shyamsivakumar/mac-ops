import contextlib
import fcntl
import math
import os
import re
import signal
import sys
import threading
import time

import inbox
import inbox_outbox as outbox
import inbox_replay
import journal

SESSION = "coordinator"
MAX_BODY = 4000
SEND = re.compile(r"^SEND\s+([^:\s]+):\s*(\S.*)$")
NOTHING = re.compile(r"^NOTHING:\s*(\S.*)$")
ZEROS = {"batches": 0, "lines": 0}
HEARTBEAT = "inbox.worker.heartbeat"
PASS_END = "inbox.worker.pass_end"
LOCK = "inbox.worker.lock"
HEARTBEAT_STALE = 240
PASS_STALE = 300
PASS_ALARM = 1200
BEAT = 30


class ModelUnavailable(Exception):
    pass


class PassTimeout(BaseException):
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


def _write(path, value):
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w") as handle:
        handle.write(repr(float(value)))
    os.replace(tmp, path)


def heartbeat(*, now, ended=False):
    d = os.path.dirname(inbox._db_path())
    _write(os.path.join(d, HEARTBEAT), now)
    if ended:
        _write(os.path.join(d, PASS_END), now)


def _beat(stop, interval, clock):
    while not stop.wait(interval):
        heartbeat(now=clock())


def _take(lock, retry_delay):
    for attempt in (0, 1):
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            if attempt:
                break
            time.sleep(retry_delay)
    return False


def _on_alarm(signum, frame):
    raise PassTimeout()


@contextlib.contextmanager
def _running(lock_path, *, now, retry_delay, alarm_seconds, beat_seconds, clock):
    with open(lock_path, "w") as lock:
        if not _take(lock, retry_delay):
            yield False
            return
        heartbeat(now=now)
        stop = threading.Event()
        threading.Thread(target=_beat, args=(stop, beat_seconds, clock), daemon=True).start()
        armed = threading.current_thread() is threading.main_thread()
        old_handler, old_timer, started = None, None, 0.0
        if armed:
            old_handler = signal.signal(signal.SIGALRM, _on_alarm)
            old_timer = signal.setitimer(signal.ITIMER_REAL, alarm_seconds)
            started = time.monotonic()
        try:
            yield True
        except PassTimeout:
            journal.emit("inbox_run_failed", "inbox_worker", reason="pass timeout")
        finally:
            stop.set()
            if armed:
                signal.setitimer(signal.ITIMER_REAL, 0)
                if old_timer is not None:
                    signal.setitimer(signal.ITIMER_REAL,
                                     max(0.0, old_timer[0] - (time.monotonic() - started)), old_timer[1])
                signal.signal(signal.SIGALRM, old_handler)
            heartbeat(now=clock(), ended=True)


def shadow_pass(*, now, runner=shadow_runner, retry_delay=0.2, alarm_seconds=PASS_ALARM,
                beat_seconds=BEAT, clock=time.time):
    lock_path = os.path.join(os.path.dirname(inbox._db_path()), "inbox.worker.lock")
    with _running(lock_path, now=now, retry_delay=retry_delay, alarm_seconds=alarm_seconds,
                  beat_seconds=beat_seconds, clock=clock) as held:
        if not held:
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
        except PassTimeout:
            inbox.release(rows, count_attempt=True)
            inbox.set_last_run(now=now)
            raise
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
    return dict(ZEROS)


def liveness(*, now, lock_held, heartbeat, last_pass_end, expect_passes):
    if lock_held:
        if heartbeat is None or now - heartbeat > HEARTBEAT_STALE:
            return "inbox worker holds its lock but its heartbeat is stale or unreadable"
        return None
    if not expect_passes:
        return None
    last = last_pass_end if last_pass_end is not None else heartbeat
    if last is None:
        return None
    if now - last > PASS_STALE:
        return "inbox worker finished no pass in over 5 minutes"
    return None


def _inbox_dir():
    return os.environ.get("COORD_INBOX_DIR") or os.path.expanduser("~/.local/state/coordinator")


def _stamp(name):
    try:
        with open(os.path.join(_inbox_dir(), name)) as handle:
            value = float(handle.read())
    except (OSError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def _lock_held(path):
    try:
        handle = open(path)
    except OSError:
        return False
    with handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def watch(*, now):
    d = _inbox_dir()
    return liveness(now=now, lock_held=_lock_held(os.path.join(d, LOCK)),
                    heartbeat=_stamp(HEARTBEAT), last_pass_end=_stamp(PASS_END),
                    expect_passes=os.environ.get("COORD_INBOX_EXPECT_PASSES", "0") not in ("", "0"))
