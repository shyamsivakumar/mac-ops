import hashlib
import json
import os

import inbox

NOTICE_PREFIX = "notice-"
OWN_NOTICE = "kind='request_notice' AND dedupe_key LIKE 'notice-%'"
CLOSED_NOTICE = "(" + OWN_NOTICE + " AND COALESCE(reason,'')='closed')"

KINDS = ("hc_send", "coordq_send", "request_notice", "none")


def shadow_on():
    return os.environ.get("COORD_INBOX_SHADOW") != "0"


def _insert(conn, run_id, index, kind, target, body, reason, now):
    if kind not in KINDS or run_id.startswith(NOTICE_PREFIX) or (kind == "none" and not (reason or "").strip()):
        raise ValueError(kind)
    return conn.execute(
        "INSERT OR IGNORE INTO outbox"
        " (ts, run_id, kind, target, body, reason, dedupe_key) VALUES (?,?,?,?,?,?,?)",
        (now, run_id, kind, target, body, reason, f"{run_id}:{index}"),
    ).rowcount == 1


def add(run_id, index, kind, target, body, *, reason=None, now):
    with inbox.txn() as conn:
        return _insert(conn, run_id, index, kind, target, body, reason, now)


def _claim(skip, clock, lease):
    marks = ",".join("?" * len(skip))
    with inbox.txn() as conn:
        row = conn.execute(
            "SELECT * FROM outbox WHERE status='pending' AND NOT %s AND id NOT IN (%s) ORDER BY id LIMIT 1" % (CLOSED_NOTICE, marks),
            tuple(skip),
        ).fetchone()
        if row is None:
            return None
        now = clock()
        if row["kind"] == "none":
            conn.execute("UPDATE outbox SET status='sent', sent_ts=? WHERE id=?", (now, row["id"]))
            return dict(row), None
        attempts, lease_until = row["attempts"] + 1, now + lease
        conn.execute(
            "UPDATE outbox SET status='sending', attempts=?, lease_until=? WHERE id=?",
            (attempts, lease_until, row["id"]),
        )
        return dict(row, attempts=attempts, lease_until=lease_until), (attempts, lease_until)


def drain(sender, *, now, shadow=None, lease=600, limit=50, clock=None):
    if shadow is None:
        shadow = shadow_on()
    if shadow:
        with inbox.txn() as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM outbox WHERE status='pending' AND kind!='none' AND NOT " + CLOSED_NOTICE
            ).fetchone()[0]
        return {"would_send": n}
    clock = clock or (lambda: now)
    sent = errors = 0
    skip = [-1]
    for _ in range(limit):
        claimed = _claim(skip, clock, lease)
        if claimed is None:
            break
        row, token = claimed
        if token is None:
            sent += 1
            continue
        try:
            sender(row)
        except Exception:
            errors += 1
            skip.append(row["id"])
            continue
        with inbox.txn() as conn:
            sent += conn.execute(
                "UPDATE outbox SET status='sent', sent_ts=? WHERE id=? AND status='sending'"
                " AND attempts=? AND lease_until=?",
                (clock(), row["id"], *token),
            ).rowcount
    return {"sent": sent, "errors": errors}


def reap(*, now):
    unknown, extra = 0, {}
    with inbox.txn() as conn:
        rows = conn.execute(
            "SELECT id, kind, attempts FROM outbox WHERE status='sending' AND lease_until < ?",
            (now,),
        ).fetchall()
        for row in rows:
            if row["kind"] == "hc_send":
                conn.execute("UPDATE outbox SET status='unknown' WHERE id=?", (row["id"],))
                unknown += 1
                continue
            key = "requeued" if row["attempts"] < 3 else "failed"
            conn.execute(
                "UPDATE outbox SET status=?, lease_until=NULL WHERE id=?",
                ("pending" if key == "requeued" else "failed", row["id"]),
            )
            extra[key] = extra.get(key, 0) + 1
    return {"unknown": unknown, **extra}


REISSUE_AFTER = 86400


def _notice_key(repo, pr, head, action, again=False):
    digest = hashlib.sha256(json.dumps([repo, pr, head, action]).encode()).hexdigest()
    return NOTICE_PREFIX + digest + ("-again" if again else "")


def _insert_notice(conn, run_id, repo, pr, head, action, ts, again):
    return conn.execute(
        "INSERT OR IGNORE INTO outbox (ts, run_id, kind, target, body, dedupe_key) VALUES (?,?,?,?,?,?)",
        (ts, run_id, "request_notice", "%s#%s" % (repo, pr),
         json.dumps({"repo": repo, "pr": pr, "head": head, "action": action}),
         _notice_key(repo, pr, head, action, again)),
    ).rowcount == 1


def request_notice(run_id, index, repo, pr, head, action, *, now):
    with inbox.txn() as conn:
        return _insert_notice(conn, run_id, repo, pr, head, action, now, False)


def close_requests(*, now):
    closed = 0
    with inbox.txn() as conn:
        rows = conn.execute(
            "SELECT id, ts, body FROM outbox WHERE " + OWN_NOTICE + " AND reason IS NOT 'closed'"
        ).fetchall()
        for row in rows:
            notice = json.loads(row["body"])
            merged = conn.execute(
                "SELECT 1 FROM inbox WHERE kind='pr_merged' AND repo=? AND pr=? AND ts>=? LIMIT 1",
                (notice["repo"], notice["pr"], row["ts"]),
            ).fetchone()
            if merged:
                closed += conn.execute(
                    "UPDATE outbox SET reason='closed' WHERE id=?", (row["id"],)
                ).rowcount
    return closed


def reissue_due(*, now):
    raised = 0
    with inbox.txn() as conn:
        rows = conn.execute(
            "SELECT run_id, ts, body, dedupe_key FROM outbox"
            " WHERE " + OWN_NOTICE + " AND reason IS NOT 'closed' AND dedupe_key NOT LIKE '%-again'"
            " AND ts < ?",
            (now - REISSUE_AFTER,),
        ).fetchall()
        for row in rows:
            n = json.loads(row["body"])
            raised += _insert_notice(
                conn, row["run_id"], n["repo"], n["pr"], n["head"], n["action"], row["ts"], True
            )
    return raised
