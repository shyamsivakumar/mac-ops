"""Unit tests for MO-124 session traces (no live T3 DB required)."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from session_traces.collect import collect_runs
from session_traces.eval_day import evaluate_day, score_trace, write_day_report
from session_traces.scrub import scrub_path, scrub_string, scrub_trace
from session_traces.store import export_posthog, load_day_traces, write_trace


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE projection_projects (
          project_id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          workspace_root TEXT NOT NULL,
          scripts_json TEXT NOT NULL DEFAULT '[]',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          deleted_at TEXT
        );
        CREATE TABLE orchestration_v2_projection_threads (
          thread_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          title TEXT NOT NULL,
          default_provider TEXT NOT NULL,
          runtime_mode TEXT NOT NULL,
          interaction_mode TEXT NOT NULL,
          active_provider_thread_id TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          archived_at TEXT,
          deleted_at TEXT,
          payload_json TEXT NOT NULL,
          provider_instance_id TEXT
        );
        CREATE TABLE orchestration_v2_projection_runs (
          run_id TEXT PRIMARY KEY,
          thread_id TEXT NOT NULL,
          ordinal INTEGER NOT NULL,
          provider TEXT NOT NULL,
          provider_thread_id TEXT,
          status TEXT NOT NULL,
          requested_at TEXT NOT NULL,
          completed_at TEXT,
          payload_json TEXT NOT NULL,
          provider_instance_id TEXT
        );
        CREATE TABLE orchestration_v2_projection_turn_items (
          turn_item_id TEXT PRIMARY KEY,
          thread_id TEXT NOT NULL,
          run_id TEXT,
          node_id TEXT,
          provider_thread_id TEXT,
          provider_turn_id TEXT,
          parent_item_id TEXT,
          ordinal INTEGER NOT NULL,
          type TEXT NOT NULL,
          status TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          payload_json TEXT NOT NULL
        );
        """
    )
    now = "2026-11-03T16:00:00.000Z"
    conn.execute(
        "INSERT INTO projection_projects VALUES (?,?,?,?,?,?,?)",
        (
            "proj1",
            "mac-ops",
            "/Users/shyamsivakumar/Code/mac-ops",
            "[]",
            now,
            now,
            None,
        ),
    )
    thread_payload = {
        "worktreePath": "/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-abc",
        "branch": "work/124",
        "pullRequests": [
            {
                "url": "https://github.com/shyamsivakumar/mac-ops/pull/99",
                "repository": "shyamsivakumar/mac-ops",
                "number": 99,
                "snapshot": {
                    "state": "merged",
                    "mergedAt": "2026-11-03T16:30:00Z",
                    "checksState": "passing",
                    "reviewDecision": None,
                    "mergeCommitOid": "deadbeef",
                    "title": "MO-124: session traces",
                },
            }
        ],
    }
    conn.execute(
        "INSERT INTO orchestration_v2_projection_threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "thread1",
            "proj1",
            "MO-124 · session traces",
            "cursor",
            "full-access",
            "default",
            None,
            now,
            now,
            None,
            None,
            json.dumps(thread_payload),
            "cursor",
        ),
    )
    run_payload = {
        "startedAt": "2026-11-03T16:00:01.000Z",
        "completedAt": "2026-11-03T16:20:00.000Z",
        "modelSelection": {"instanceId": "cursor", "model": "default"},
    }
    conn.execute(
        "INSERT INTO orchestration_v2_projection_runs VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "run1",
            "thread1",
            1,
            "cursor",
            None,
            "completed",
            "2026-11-03T16:00:00.000Z",
            "2026-11-03T16:20:00.000Z",
            json.dumps(run_payload),
            "cursor",
        ),
    )
    tools = [
        (
            "item1",
            "dynamic_tool",
            {
                "toolName": "mcp__t3-code__link_pull_request",
                "startedAt": "2026-11-03T16:01:00.000Z",
                "completedAt": "2026-11-03T16:01:01.500Z",
                "status": "completed",
                "input": {"url": "https://example.com?token=sk-EXAMPLEEXAMP"},
            },
        ),
        (
            "item2",
            "file_change",
            {
                "fileName": "/Users/shyamsivakumar/Code/other-repo/secret.env",
                "startedAt": "2026-11-03T16:02:00.000Z",
                "completedAt": "2026-11-03T16:02:00.100Z",
                "status": "completed",
            },
        ),
        (
            "item3",
            "dynamic_tool",
            {
                "toolName": "html_preview",
                "startedAt": "2026-11-03T16:03:00.000Z",
                "completedAt": "2026-11-03T16:03:02.000Z",
                "status": "completed",
            },
        ),
    ]
    for i, (item_id, typ, payload) in enumerate(tools):
        conn.execute(
            "INSERT INTO orchestration_v2_projection_turn_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                item_id,
                "thread1",
                "run1",
                None,
                None,
                None,
                None,
                i,
                typ,
                "completed",
                now,
                json.dumps(payload),
            ),
        )
    conn.commit()
    conn.close()


class ScrubTests(unittest.TestCase):
    def test_redacts_keys_and_home(self):
        s = scrub_string(
            "key=phc_abc123 token=sk-EXAMPLE email me@example.com /Users/shyamsivakumar/Code/x"
        )
        self.assertNotIn("phc_abc123", s)
        self.assertNotIn("sk-EXAMPLE", s)
        self.assertNotIn("me@example.com", s)
        self.assertIn("/Users/[user]", s)

    def test_drops_prompt_fields(self):
        out = scrub_trace({"prompt": "secret brief", "run_id": "r1", "api_key": "x"})
        self.assertNotIn("prompt", out)
        self.assertNotIn("api_key", out)
        self.assertEqual(out["run_id"], "r1")

    def test_scrub_path(self):
        self.assertEqual(
            scrub_path("/Users/shyamsivakumar/.t3/worktrees/x"),
            "/Users/[user]/.t3/worktrees/x",
        )


class CollectEvalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "state.sqlite"
        _make_db(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_collect_builds_trace(self):
        traces = collect_runs(
            since=datetime(2026, 11, 3, tzinfo=timezone.utc),
            until=datetime(2026, 11, 4, tzinfo=timezone.utc),
            db_path=self.db,
        )
        self.assertEqual(len(traces), 1)
        t = traces[0]
        self.assertEqual(t["task_key"], "MO-124")
        self.assertEqual(t["provider"], "cursor")
        self.assertEqual(t["model"], "default")
        self.assertEqual(t["status"], "completed")
        self.assertEqual(t["tool_call_count"], 3)
        self.assertTrue(t["files_outside_worktree"])
        self.assertIn("html_preview", t["preview_or_playwright"])
        self.assertEqual(t["pull_requests"][0]["state"], "merged")
        # Tool inputs (secrets) must not appear on the trace.
        blob = json.dumps(t)
        self.assertNotIn("sk-secret", blob)

    def test_store_and_eval(self):
        traces = collect_runs(
            since=datetime(2026, 11, 3, tzinfo=timezone.utc),
            until=datetime(2026, 11, 4, tzinfo=timezone.utc),
            db_path=self.db,
        )
        write_trace(traces[0], root=self.root)
        loaded = load_day_traces("2026-11-03", root=self.root)
        self.assertEqual(len(loaded), 1)
        scored = score_trace(loaded[0])
        self.assertTrue(scored["merged_pr"])
        self.assertTrue(scored["claimed_done_with_proof"])
        self.assertIn("files_outside_worktree", scored["flags"])
        self.assertIn("preview_or_playwright", scored["flags"])
        self.assertNotIn("claimed_done_without_proof", scored["flags"])
        report = write_day_report("2026-11-03", root=self.root)
        self.assertTrue(Path(report["md"]).is_file())
        summary = evaluate_day("2026-11-03", root=self.root)
        self.assertEqual(summary["run_count"], 1)
        self.assertEqual(summary["merged_pr_count"], 1)
        self.assertEqual(summary["claimed_done_with_proof"], 1)

    def test_posthog_dry_run_and_skip(self):
        self.assertEqual(
            export_posthog([{"run_id": "r"}], api_key=None)["skipped"], "no_api_key"
        )
        out = export_posthog(
            [{"run_id": "r", "thread_id": "t"}], api_key="phc_test", dry_run=True
        )
        self.assertEqual(out["exported"], 1)
        self.assertTrue(out["dry_run"])


if __name__ == "__main__":
    unittest.main()
