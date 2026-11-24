import json
import math
import os
import re

import inbox
import journal


def activate(*, now):
    with inbox.txn() as conn:
        conn.execute("INSERT OR IGNORE INTO meta (k, v) VALUES ('activated_at', ?)", (str(now),))


def _value(conn, key, default=None):
    row = conn.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
    return default if row is None else row[0]


JOURNAL_FILE = re.compile(r"events-\d{4}-\d{2}\.jsonl")


def _scalar(value):
    return value is None or isinstance(value, (str, int)) and not isinstance(value, bool)


def _valid(row):
    ts = row.get("ts") if isinstance(row, dict) else None
    return (
        isinstance(row, dict)
        and isinstance(ts, (int, float))
        and not isinstance(ts, bool)
        and math.isfinite(ts)
        and isinstance(row.get("event"), str)
        and isinstance(row.get("data"), (dict, type(None)))
        and all(_scalar(row.get(k)) for k in ("repo", "pr", "head", "ticket"))
    )


def replay():
    counts = {"enqueued": 0, "seen_only": 0, "skipped": 0}
    with inbox.txn() as conn:
        activated = _value(conn, "activated_at")
        if activated is None:
            raise RuntimeError("inbox not activated")
        since = float(activated)
        directory = journal.journal_dir()
        names = sorted(os.listdir(directory)) if os.path.isdir(directory) else []
        for name in filter(JOURNAL_FILE.fullmatch, names):
            offset = int(_value(conn, "replay_off:" + name, 0))
            with open(os.path.join(directory, name), "rb") as fh:
                fh.seek(offset)
                data = fh.read()
            cut = data.rfind(b"\n") + 1
            for line in data[:cut].split(b"\n")[:-1]:
                try:
                    row = json.loads(line)
                except ValueError:
                    counts["skipped"] += 1
                    continue
                if not _valid(row):
                    counts["skipped"] += 1
                    continue
                counts[inbox.apply_journal(conn, row, since=since)] += 1
            conn.execute(
                "INSERT INTO meta (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                ("replay_off:" + name, str(offset + cut)),
            )
    return counts
