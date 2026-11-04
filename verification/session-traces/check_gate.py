"""Replay MO-124 safety gate locally; HTTP is always mocked."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from session_traces.empryo import collect_empryo
from session_traces.collect import _unfinished_run_ids
from session_traces.scrub import scrub_trace
from session_traces.store import export_posthog, write_trace


def main():
    secret = "hf_" + "a" * 32
    trace = {"source": "empryo", "run_id": "synthetic", "model": "proxy/" + secret,
             "title": "PRIVATE MESSAGE " + secret, "nested": {"messageBody": "PRIVATE MESSAGE"}}
    captures = []
    def capture(request, **kwargs):
        captures.append(json.loads(request.data))
        response = MagicMock()
        response.__enter__.return_value.status = 200
        return response
    with patch("urllib.request.urlopen", capture):
        for _ in range(2):
            assert export_posthog([trace], api_key="synthetic-key")["exported"] == 1
    blob = json.dumps(captures)
    assert secret not in blob and "PRIVATE MESSAGE" not in blob
    assert "title" not in scrub_trace(trace)
    ids = [batch["batch"][0]["uuid"] for batch in captures]
    assert ids[0] == ids[1] and UUID(ids[0])
    print("privacy: secret/title/message absent; HTTP mocked")
    print("event UUID: stable across two captures", ids[0])
    with patch("urllib.request.urlopen", capture):
        export_posthog([dict(trace, status="running", started_at="2026-11-03T12:00:00Z")], api_key="synthetic-key")
        export_posthog([dict(trace, status="completed", started_at="2026-11-03T12:00:00Z", completed_at="2026-11-03T12:05:00Z")], api_key="synthetic-key")
    events = [batch["batch"][0] for batch in captures[-2:]]
    assert events[0]["uuid"] == events[1]["uuid"] and events[0]["timestamp"] == events[1]["timestamp"]
    print("event identity: stable through running-to-completed transition")
    assert secret not in json.dumps(scrub_trace(trace))
    now = datetime.now(timezone.utc)
    ts = int(now.timestamp() * 1000)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / "threads.db"
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE threads(id TEXT, session_dir TEXT)")
            for thread in ("one", "two"):
                folder = root / thread
                folder.mkdir()
                (folder / "meta.json").write_text(json.dumps({"id": thread, "startedAt": ts - 1000}))
                conn.execute("INSERT INTO threads VALUES (?, ?)", (thread, str(folder)))
        journal = root / "one" / "session.jsonl"
        other = root / "two" / "session.jsonl"
        user = {"k": "user", "turnId": "turn-one", "tabId": "tab", "ts": ts}
        done = {"k": "assistant", "turnId": "turn-one", "status": "complete", "ts": ts + 1}
        other.write_text(json.dumps(dict(user, turnId="turn-two")) + "\n" + json.dumps(dict(done, turnId="turn-two")) + "\n")
        journal.write_text(json.dumps(user) + "\n")
        original = Path.open
        class Reader:
            def __init__(self, stream): self.stream = stream
            def __enter__(self): self.stream.__enter__(); return self
            def __exit__(self, *args): return self.stream.__exit__(*args)
            def __getattr__(self, name): return getattr(self.stream, name)
            def read(self, size=-1):
                with original(journal, "a") as writer: writer.write(json.dumps(done) + "\n")
                return self.stream.read(size)
        def opening(path, *args, **kwargs):
            stream = original(path, *args, **kwargs)
            return Reader(stream) if path == journal and args and args[0] == "rb" else stream
        start, end = now - timedelta(days=1), now + timedelta(days=1)
        rid = "empryo-" + hashlib.sha256(b"turn-one").hexdigest()
        with patch.dict(os.environ, {"EMPRYO_THREADS_DB": str(db)}):
            with patch.object(Path, "open", opening):
                runs = {r["run_id"]: r for r in collect_empryo(since=start, until=end)}
            assert runs[rid]["status"] == "running"
            assert {r["run_id"]: r for r in collect_empryo(since=start, until=end)}[rid]["status"] == "completed"
            print("snapshot: appended completion deferred; next collection completed")
            journal.write_text(json.dumps(user) + "\n" + json.dumps(dict(done, status=[])) + "\n")
            runs = collect_empryo(since=start, until=end)
            assert len(runs) == 2 and {r["run_id"]: r for r in runs}[rid]["status"] == "running"
            assert next(r for r in runs if r["run_id"] != rid)["status"] == "completed"
            print("malformed status: batch survives; independent journal completed")
            old = now - timedelta(days=5)
            for status in ("running", "unknown"):
                path = write_trace({"source": "empryo", "run_id": rid, "status": status, "started_at": old.isoformat()}, root=root / "state")
                assert rid in _unfinished_run_ids(root / "state")
                assert path.name == rid + ".json"
            print("reconciliation: five-day running and unknown both eligible")
            reads = []
            def counting(path, *args, **kwargs):
                if path.name == "session.jsonl": reads.append(path)
                return original(path, *args, **kwargs)
            with patch.object(Path, "open", counting):
                assert collect_empryo(since=now-timedelta(days=30), until=now-timedelta(days=29)) == []
            assert not reads
            print("empty historical day: zero journal reads")
            for thread in ("one", "two"):
                (root / thread / "meta.json").write_text(json.dumps({"id": thread, "startedAt": ts - 1000, "updatedAt": ts}))
            reads.clear()
            class NoRead:
                def __init__(self, stream): self.stream = stream
                def __enter__(self): self.stream.__enter__(); return self
                def __exit__(self, *args): return self.stream.__exit__(*args)
                def __getattr__(self, name): return getattr(self.stream, name)
                def read(self, *args): raise AssertionError("empty future day read journal bytes")
            def future_open(path, *args, **kwargs):
                stream = original(path, *args, **kwargs)
                return NoRead(stream) if path.name == "session.jsonl" else stream
            with patch.object(Path, "open", future_open):
                assert collect_empryo(since=now+timedelta(days=29), until=now+timedelta(days=30)) == []
            print("empty future day: zero journal bytes read")
    print("PASS: all safety gate reproductions; no network export")


if __name__ == "__main__":
    main()
