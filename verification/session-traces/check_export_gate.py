"""Replay the 0eb88e6 Sol gate using synthetic data and mocked HTTP only."""
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from session_traces.empryo import collect_empryo
from session_traces.scrub import scrub_trace
from session_traces.store import export_posthog, write_trace


def main():
    now = datetime.now(timezone.utc)
    timestamp = int(now.timestamp() * 1000)
    credentials = ["AIza" + "a" * 35, "hf_" + "b" * 32, "unknown-secret-shape"]
    captures = []
    def capture(request, **kwargs):
        captures.append(json.loads(request.data))
        response = MagicMock()
        response.__enter__.return_value.status = 200
        return response
    trace = {
        "schema": "mac-ops.session_trace.v1", "source": "empryo", "run_id": "synthetic-run",
        "thread_id": "synthetic-thread", "status": "completed", "final_state": "completed",
        "started_at": "2026-11-03T12:00:00Z", "completed_at": "2026-11-03T12:05:00Z",
        "model": "proxy/gpt-6.1-terra", "provider": "proxy", "duration_ms": 300000,
        "tokens": {"inputTokens": 42, "outputTokens": 8, "totalTokens": 50},
        "pull_requests": [{"number": 50, "repository": "synthetic/repo", "state": "merged",
                           "checks_state": "passing", "review_decision": "APPROVED",
                           "merge_sha": "a" * 40, "merge_by_end": True, "timing": "known"}],
        "outcome_evidence": "known",
        "tool_calls": [{"name": "shell", "type": "tool", "status": "completed", "duration_ms": 123}],
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        folder = root / "session"
        folder.mkdir()
        db = root / "threads.db"
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE threads(id TEXT, session_dir TEXT)")
            conn.execute("INSERT INTO threads VALUES (?, ?)", ("thread", str(folder)))
        (folder / "meta.json").write_text(json.dumps({"id": "thread", "startedAt": timestamp-1}))
        for credential in credentials:
            events = [
                {"k": "tab", "tabId": "tab", "patch": {"activeModel": "proxy/"+credential}, "ts": timestamp},
                {"k": "user", "tabId": "tab", "turnId": "turn", "ts": timestamp+1},
                {"k": "assistant", "turnId": "turn", "status": "complete", "ts": timestamp+2},
            ]
            (folder / "session.jsonl").write_text("\n".join(json.dumps(e) for e in events)+"\n")
            with patch.dict(os.environ, {"EMPRYO_THREADS_DB": str(db)}):
                collected = collect_empryo(since=now-timedelta(days=1), until=now+timedelta(days=1))
            assert len(collected) == 1 and collected[0]["model"] is None
            malicious = dict(trace, model="proxy/"+credential, title="PRIVATE MESSAGE", body="PRIVATE MESSAGE")
            local = write_trace(malicious, root=root / "state")
            assert credential not in local.read_text() and "PRIVATE MESSAGE" not in local.read_text()
            assert scrub_trace(malicious)["model"] is None
            with patch("urllib.request.urlopen", capture):
                assert export_posthog([malicious], api_key="synthetic-key")["exported"] == 1
            blob = json.dumps(captures[-1])
            assert credential not in blob and "PRIVATE MESSAGE" not in blob
        print("credential_shape_survives_local: false (AIza, HF, arbitrary unknown)")
        print("credential_shape_survives_mock_capture: false")
    captures.clear()
    with patch("urllib.request.urlopen", capture):
        running = dict(trace, status="running", final_state="running", completed_at=None)
        result = export_posthog([running], api_key="synthetic-key")
        assert result["exported"] == 0 and not captures
        assert export_posthog([trace], api_key="synthetic-key")["exported"] == 1
        assert export_posthog([trace], api_key="synthetic-key")["exported"] == 1
        before = len(captures)
        assert export_posthog([dict(trace, status="unknown")], api_key="synthetic-key")["exported"] == 0
        assert export_posthog([{"run_id": "missing-status"}], api_key="synthetic-key")["exported"] == 0
        assert len(captures) == before
    first_wins = {}
    for batch in captures:
        for event in batch["batch"]:
            first_wins.setdefault(event["uuid"], event)
    assert len(first_wins) == 1
    assert next(iter(first_wins.values()))["properties"]["status"] == "completed"
    print("first-event-wins: completed; running/unknown/missing-status deferred")
    event = next(iter(first_wins.values()))
    properties = event["properties"]
    for field in ("tokens", "pull_requests", "outcome_evidence", "tool_calls_summary"):
        assert field in properties, field
    assert properties["tokens"]["totalTokens"] == 50
    assert properties["pull_requests"][0]["number"] == 50
    assert properties["outcome_evidence"] == "known"
    assert properties["tool_calls_summary"][0]["name"] == "shell"
    assert properties["tool_calls_summary"][0]["duration_ms"] == 123
    print("trace detail: tokens=50, PR=50, outcome=known, shell duration_ms=123")
    print("PASS: three Sol gate reproductions; no network trace exports")


if __name__ == "__main__":
    main()
