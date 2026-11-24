import contextlib
import fcntl
import json
import os
import sqlite3
import time
import uuid

KINDS = frozenset(
    "pr_opened pr_new_head pr_merged pr_review gate_verdict gate_queued ci_main human_signal "
    "timer_due alarm round_cap merge_held close_failed launch_failed recut".split()
)
WAKE = "alarm,round_cap,merge_held,close_failed,launch_failed,recut,human_signal,timer_due"
STATUSES = ("pending", "claimed", "done", "failed")
CLEAR = "run_id=NULL, claimed_by=NULL, claimed_pid=NULL, lease_until=NULL"
SCHEMA = (
    """CREATE TABLE IF NOT EXISTS inbox(
        id INTEGER PRIMARY KEY, ts REAL, source TEXT, kind TEXT, dedupe_key TEXT UNIQUE,
        session TEXT, repo TEXT, pr INTEGER, head TEXT, payload TEXT,
        status TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0, claimed_by TEXT,
        claimed_pid INTEGER, lease_until REAL, run_id TEXT, tier TEXT, done_ts REAL,
        error TEXT)""",
    """CREATE TABLE IF NOT EXISTS seen(
        key TEXT PRIMARY KEY, ts REAL)""",
    """CREATE TABLE IF NOT EXISTS meta(
        k TEXT PRIMARY KEY, v TEXT)""",
    """CREATE TABLE IF NOT EXISTS timers(
        id TEXT PRIMARY KEY, due_ts REAL, period REAL, payload TEXT)""",
    """CREATE TABLE IF NOT EXISTS outbox(
        id INTEGER PRIMARY KEY, ts REAL, run_id TEXT, kind TEXT, target TEXT, body TEXT,
        reason TEXT, dedupe_key TEXT UNIQUE, status TEXT DEFAULT 'pending',
        attempts INTEGER DEFAULT 0, lease_until REAL, sent_ts REAL)""",
)
DB_NAME = "inbox.db"
JOURNAL_KINDS = {
    "gate_queued": "gate_queued",
    "gate_verdict": "gate_verdict",
    "merged": "pr_merged",
    "merged_outside_lane": "pr_merged",
    "alarm_raised": "alarm",
    "round_cap": "round_cap",
    "merge_held": "merge_held",
    "close_failed": "close_failed",
    "launch_failed": "launch_failed",
    "recut": "recut",
}


def _db_path():
    path = os.environ.get("COORD_INBOX_DIR") or os.path.expanduser("~/.local/state/coordinator")
    os.makedirs(path, exist_ok=True)
    return os.path.join(path, DB_NAME)


def _read_version(conn):
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _remaining_ms(deadline):
    return max(0, int((deadline - time.monotonic()) * 1000))


def _lock_wait(lock, deadline):
    while True:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise TimeoutError(lock.name) from None
            time.sleep(0.01)


def _begin(conn, deadline):
    if deadline is not None:
        conn.execute("PRAGMA busy_timeout = %d" % _remaining_ms(deadline))
    conn.execute("BEGIN IMMEDIATE")


def _init(conn, deadline=None):
    _begin(conn, deadline)
    try:
        if _read_version(conn) == 0:
            for statement in SCHEMA:
                conn.execute(statement)
            conn.execute("PRAGMA user_version=1")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def connect(deadline=None):
    path = _db_path()
    timeout = 30 if deadline is None else _remaining_ms(deadline) / 1000
    conn = sqlite3.connect(path, isolation_level=None, timeout=timeout)
    conn.row_factory = sqlite3.Row
    try:
        if _read_version(conn) == 0:
            with open(path + ".init", "w") as lock:
                if deadline is None:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                else:
                    _lock_wait(lock, deadline)
                conn.execute("PRAGMA journal_mode=WAL")
                _init(conn, deadline)
        version = _read_version(conn)
        if version != 1:
            raise RuntimeError("unsupported inbox user_version: %r" % (version,))
    except BaseException:
        conn.close()
        raise
    return conn


@contextlib.contextmanager
def txn(deadline=None):
    conn = connect(deadline)
    _begin(conn, deadline)
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def enqueue(kind, key, *, source, ts, session="coordinator", repo=None, pr=None, head=None,
            payload=None, tier=None):
    with txn() as conn:
        return _insert(conn, kind, key, source=source, ts=ts, session=session, repo=repo, pr=pr,
                       head=head, payload=payload, tier=tier)


def _insert(conn, kind, key, *, source, ts, session="coordinator", repo=None, pr=None, head=None,
            payload=None, tier=None):
    if kind not in KINDS:
        raise ValueError(kind)
    wake = frozenset((os.environ.get("COORD_INBOX_WAKE_KINDS") or WAKE).split(","))
    tier = tier or ("wake" if kind in wake else "batch")
    seen = conn.execute("INSERT OR IGNORE INTO seen(key, ts) VALUES (?, ?)", (key, ts))
    if seen.rowcount == 0:
        return False
    conn.execute(
        "INSERT INTO inbox (ts, source, kind, dedupe_key, session, repo, pr, head, payload, tier)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (ts, source, kind, key, session, repo, pr, head,
         None if payload is None else json.dumps(payload), tier),
    )
    return True


def _alarm_gen(conn, name):
    row = conn.execute("SELECT v FROM meta WHERE k=?", ("alarm_gen:" + str(name),)).fetchone()
    return 0 if row is None else int(row[0])


def from_journal(conn, row):
    data = row.get("data") or {}
    event = row["event"]
    if event == "alarm_withdrawn":
        conn.execute(
            "INSERT INTO meta (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            ("alarm_gen:" + str(data.get("alarm")), str(_alarm_gen(conn, data.get("alarm")) + 1)),
        )
        return None
    kind = JOURNAL_KINDS.get(event)
    if kind is None:
        return None
    pr, ticket = row.get("pr"), row.get("ticket")
    num = pr if pr is not None else ticket if ticket is not None else ""
    payload = None
    if kind == "alarm":
        name = data.get("alarm")
        gen = _alarm_gen(conn, name)
        key = f"alarm:{name}:{gen}"
        payload = {"alarm": name, "generation": gen}
    else:
        key = f"{kind}:{row.get('repo') or ''}#{num}:{row.get('head') or ''}"
    return dict(
        kind=kind,
        key=key,
        source="journal",
        ts=row["ts"],
        repo=row.get("repo"),
        pr=pr if pr is not None else ticket,
        head=row.get("head"),
        payload=payload,
    )


def record_journal(row, *, wait):
    deadline = time.monotonic() + wait
    with txn(deadline) as conn:
        event = from_journal(conn, row)
        if event:
            _insert(conn, event.pop("kind"), event.pop("key"), **event)


FALLBACK_ID = "fallback"


def _fallback_seconds():
    return float(os.environ.get("COORD_INBOX_FALLBACK_SECONDS") or 7200)


def _set_meta(conn, k, v):
    conn.execute(
        "INSERT INTO meta (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
        (k, v),
    )


def _last_run(conn):
    row = conn.execute("SELECT v FROM meta WHERE k=?", ("last_run",)).fetchone()
    return None if row is None else float(row[0])


def add_timer(id, *, due_ts, period=None, payload=None):
    if period is not None and period <= 0:
        raise ValueError(period)
    with txn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO timers (id, due_ts, period, payload) VALUES (?,?,?,?)",
            (id, due_ts, period, None if payload is None else json.dumps(payload)),
        )


def cancel_timer(id):
    with txn() as conn:
        conn.execute("DELETE FROM timers WHERE id=?", (id,))


def set_last_run(*, now):
    with txn() as conn:
        _set_meta(conn, "last_run", now)


def ensure_fallback(*, now):
    with txn() as conn:
        last = _last_run(conn)
        secs = _fallback_seconds()
        conn.execute(
            "INSERT OR IGNORE INTO timers (id, due_ts, period, payload) VALUES (?,?,?,?)",
            (FALLBACK_ID, (last if last is not None else now) + secs, secs, None),
        )


def enqueue_due_timers(*, now):
    count = 0
    with txn() as conn:
        last, secs = _last_run(conn), _fallback_seconds()
        rows = conn.execute(
            "SELECT id, due_ts, period, payload FROM timers WHERE due_ts <= ? ORDER BY due_ts",
            (now,),
        ).fetchall()
        for row in rows:
            timer, due_ts, period, payload = row[0], row[1], row[2], row[3]
            if timer == FALLBACK_ID and last is not None and now - last < secs:
                conn.execute(
                    "UPDATE timers SET due_ts=? WHERE id=?", (last + secs, timer)
                )
                continue
            extra = json.loads(payload) if payload else {}
            if _insert(
                conn,
                "timer_due",
                f"timer_due:{timer}:{due_ts}",
                source="timer",
                ts=now,
                payload={"timer": timer, **extra},
            ):
                count += 1
            if period:
                conn.execute(
                    "UPDATE timers SET due_ts=? WHERE id=?",
                    ((now // period + 1) * period, timer),
                )
            else:
                conn.execute("DELETE FROM timers WHERE id=?", (timer,))
    return count


def claim(session, *, worker, now, lease=900, limit=50, pid=None):
    with txn() as conn:
        ids = [
            row[0]
            for row in conn.execute(
                "SELECT id FROM inbox WHERE status='pending' AND session=? ORDER BY id LIMIT ?",
                (session, limit),
            )
        ]
        token = uuid.uuid4().hex
        for row_id in ids:
            conn.execute(
                "UPDATE inbox SET status='claimed', claimed_by=?, claimed_pid=?, lease_until=?,"
                " attempts=attempts+1, run_id=? WHERE id=? AND status='pending'",
                (worker, pid, now + lease, token, row_id),
            )
        rows = conn.execute("SELECT * FROM inbox WHERE run_id=? ORDER BY id", (token,)).fetchall()
    return [
        dict(row, payload=None if row["payload"] is None else json.loads(row["payload"]))
        for row in rows
    ]


def _update(rows, sql, extra=()):
    with txn() as conn:
        return sum(
            conn.execute(sql, tuple(extra) + (row["id"], row["run_id"])).rowcount for row in rows
        )


def ack(rows, *, now):
    return _update(
        rows,
        "UPDATE inbox SET status='done', done_ts=?, lease_until=NULL"
        " WHERE id=? AND run_id=? AND status='claimed'",
        (now,),
    )


def release(rows, *, count_attempt):
    sql = "UPDATE inbox SET status='pending', " + CLEAR
    sql += "" if count_attempt else ", attempts=attempts-1"
    return _update(rows, sql + " WHERE id=? AND run_id=? AND status='claimed'")


def _alive(pid):
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def reap(*, now):
    with txn() as conn:
        n = 0
        rows = conn.execute(
            "SELECT id, claimed_pid, lease_until, attempts FROM inbox"
            " WHERE status='claimed' AND lease_until < ?",
            (now,),
        ).fetchall()
        for row in rows:
            if not (now - row["lease_until"] > 3600 or not _alive(row["claimed_pid"])):
                continue
            if row["attempts"] >= 3:
                conn.execute(
                    "UPDATE inbox SET status='failed', error='attempts', done_ts=?, " + CLEAR
                    + " WHERE id=?",
                    (now, row["id"]),
                )
            else:
                conn.execute(
                    "UPDATE inbox SET status='pending', " + CLEAR + " WHERE id=?",
                    (row["id"],),
                )
            n += 1
        return n


def counts():
    with contextlib.closing(connect()) as conn:
        rows = conn.execute("SELECT status, COUNT(*) FROM inbox GROUP BY status").fetchall()
    return {**dict.fromkeys(STATUSES, 0), **dict(rows)}
