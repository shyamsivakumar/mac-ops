import json
import os

import inbox
import journal


def activate(*, now):
    with inbox.txn() as conn:
        conn.execute("INSERT OR IGNORE INTO meta (k, v) VALUES ('activated_at', ?)", (str(now),))


def _value(conn, key, default=None):
    row = conn.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
    return default if row is None else row[0]


def replay():
    counts = {"enqueued": 0, "seen_only": 0, "skipped": 0}
    with inbox.txn() as conn:
        activated = _value(conn, "activated_at")
        if activated is None:
            raise RuntimeError("inbox not activated")
        since = float(activated)
        directory = journal.journal_dir()
        for name in sorted(os.listdir(directory)):
            if not name.startswith("events-") or not name.endswith(".jsonl"):
                continue
            offset = int(_value(conn, "replay_off:" + name, 0))
            with open(os.path.join(directory, name), "rb") as fh:
                fh.seek(offset)
                data = fh.read()
            cut = data.rfind(b"\n") + 1
            for line in data[:cut].splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    counts["skipped"] += 1
                    continue
                if not isinstance(row, dict) or "event" not in row or "ts" not in row:
                    counts["skipped"] += 1
                    continue
                counts[inbox.apply_journal(conn, row, since=since)] += 1
            conn.execute(
                "INSERT INTO meta (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                ("replay_off:" + name, str(offset + cut)),
            )
    return counts
