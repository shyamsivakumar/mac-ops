"""Replay legacy PR-content injection through daily JSON and evidence copy."""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.test_session_traces import _make_db
from session_traces.collect import collect_and_store
from session_traces.eval_day import write_day_report


def main():
    credential = "AIza" + "x" * 35
    private = "PRIVATE PROMPT"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / "legacy.db"
        _make_db(db)
        with sqlite3.connect(db) as conn:
            payload = json.loads(conn.execute("SELECT payload_json FROM orchestration_v2_projection_threads").fetchone()[0])
            pr = payload["pullRequests"][0]
            pr["repository"] = credential
            pr["snapshot"]["headBranch"] = private
            conn.execute("UPDATE orchestration_v2_projection_threads SET payload_json = ?", (json.dumps(payload),))
        state = root / "state"
        with patch.dict(os.environ, {"EMPRYO_THREADS_DB": str(root / "missing.db")}):
            result = collect_and_store(
                since=datetime(2026, 11, 3, tzinfo=timezone.utc),
                until=datetime(2026, 11, 4, tzinfo=timezone.utc),
                db_path=db, state_root=state, export=False,
            )
        assert result["collected"] == 1 and result["posthog"]["exported"] == 0
        report = write_day_report("2026-11-03", root=state)
        evidence = root / "coordinator-evidence"
        evidence.mkdir()
        for key in ("json", "md"):
            source = Path(report[key])
            target = evidence / source.name
            shutil.copy2(source, target)
            content = target.read_text()
            assert credential not in content and private not in content
        summary = json.loads(Path(report["json"]).read_text())
        assert summary["run_count"] == 1 and summary["merged_pr_count"] == 1
        assert summary["tokens_per_merged_pr"]["total"] == 3120
        from session_traces.scrub import safe_export_projection
        assert safe_export_projection({"pull_requests": [{"review_decision": "changes_requested"}]})["pull_requests"][0]["review_decision"] == "CHANGES_REQUESTED"
    print("daily JSON/Markdown/copied evidence: credential absent; private prompt absent")
    print("objective metrics retained: runs=1, merged PRs=1, tokens=3120")


if __name__ == "__main__":
    main()
