import os

import inbox

KINDS = ("hc_send", "coordq_send", "request_notice", "none")


def shadow_on():
    return os.environ.get("COORD_INBOX_SHADOW") != "0"


def add(run_id, index, kind, target, body, *, reason=None, now):
    if kind not in KINDS or (kind == "none" and reason is None):
        raise ValueError(kind)
    with inbox.txn() as conn:
        return conn.execute(
            "INSERT OR IGNORE INTO outbox"
            " (ts, run_id, kind, target, body, reason, dedupe_key) VALUES (?,?,?,?,?,?,?)",
            (now, run_id, kind, target, body, reason, f"{run_id}:{index}"),
        ).rowcount == 1


def drain(sender, *, now, shadow=None, lease=600, limit=50):
    if shadow is None:
        shadow = shadow_on()
    if shadow:
        with inbox.txn() as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM outbox WHERE status='pending' AND kind!='none'"
            ).fetchone()[0]
        return {"would_send": n}
    claimed, sent = [], 0
    with inbox.txn() as conn:
        rows = conn.execute(
            "SELECT * FROM outbox WHERE status='pending' ORDER BY id LIMIT ?", (limit,)
        ).fetchall()
        for row in rows:
            if row["kind"] == "none":
                sent += conn.execute(
                    "UPDATE outbox SET status='sent', sent_ts=? WHERE id=? AND status='pending'",
                    (now, row["id"]),
                ).rowcount
                continue
            attempts, lease_until = row["attempts"] + 1, now + lease
            ok = conn.execute(
                "UPDATE outbox SET status='sending', attempts=?, lease_until=?"
                " WHERE id=? AND status='pending'",
                (attempts, lease_until, row["id"]),
            ).rowcount
            if ok == 1:
                claimed.append((dict(row, attempts=attempts), attempts, lease_until))
    errors = 0
    for row, attempts, lease_until in claimed:
        try:
            sender(row)
        except Exception:
            errors += 1
            continue
        with inbox.txn() as conn:
            sent += conn.execute(
                "UPDATE outbox SET status='sent', sent_ts=? WHERE id=? AND status='sending'"
                " AND attempts=? AND lease_until=?",
                (now, row["id"], attempts, lease_until),
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
