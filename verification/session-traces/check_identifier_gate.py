"""Reject unencodable journal IDs without aborting a batch."""
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from session_traces.empryo import _id, collect_empryo


def main():
    assert _id("\ud800") is None
    now = datetime.now(timezone.utc)
    ts = int(now.timestamp() * 1000)
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        db = folder / "threads.db"
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE threads(id TEXT, session_dir TEXT)")
            conn.execute("INSERT INTO threads VALUES (?, ?)", ("thread", str(folder)))
        (folder / "meta.json").write_text(json.dumps({"id": "thread", "startedAt": ts}))
        events = [
            {"k": "user", "turnId": "\ud800", "ts": ts},
            {"k": "user", "turnId": "valid", "ts": ts + 1},
            {"k": "assistant", "turnId": "valid", "status": "complete", "ts": ts + 2},
        ]
        (folder / "session.jsonl").write_text("\n".join(map(json.dumps, events)) + "\n")
        with patch.dict(os.environ, {"EMPRYO_THREADS_DB": str(db)}):
            traces = collect_empryo(since=now-timedelta(days=1), until=now+timedelta(days=1))
        assert len(traces) == 1 and traces[0]["status"] == "completed"
    print("surrogate turnId: rejected; valid independent turn: completed")


if __name__ == "__main__":
    main()
