"""Unit tests for MO-124 session traces (no live T3 DB required)."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest.mock import patch

from session_traces.empryo import collect_empryo

from session_traces.__main__ import _parse_day
from session_traces.collect import (
    _allowed_roots,
    _path_under,
    _pr_outcomes_for_run,
    _tool_name,
    collect_runs,
)
from session_traces.eval_day import _merged_pr_metrics, evaluate_day, score_trace
from session_traces.scrub import scrub_path, scrub_string, scrub_trace
from session_traces.store import export_posthog, write_trace


def _make_db(
    path: Path,
    *,
    merged_at: str = "2026-11-03T16:15:00Z",
    status: str = "completed",
    completed_at: str = "2026-11-03T16:20:00.000Z",
    checks: str = "passing",
    synced_at: str | None = "2026-11-03T16:16:00Z",
    title_cmd: str | None = None,
    file_name: str = "/Users/shyamsivakumar/Code/other-repo/secret.env",
    extra_run: dict | None = None,
) -> None:
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
        CREATE TABLE orchestration_v2_projection_run_attempts (
          attempt_id TEXT PRIMARY KEY,
          thread_id TEXT NOT NULL,
          run_id TEXT NOT NULL,
          provider_thread_id TEXT NOT NULL
        );
        CREATE TABLE orchestration_v2_projection_provider_turns (
          provider_turn_id TEXT PRIMARY KEY,
          thread_id TEXT NOT NULL,
          provider_thread_id TEXT NOT NULL,
          run_attempt_id TEXT,
          ordinal INTEGER NOT NULL,
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
                    "mergedAt": merged_at,
                    "checksState": checks,
                    "reviewDecision": None,
                    "mergeCommitOid": "deadbeef",
                    "syncedAt": synced_at,
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
        "completedAt": completed_at,
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
            status,
            "2026-11-03T16:00:00.000Z",
            completed_at if status == "completed" else None,
            json.dumps(run_payload),
            "cursor",
        ),
    )
    if extra_run:
        conn.execute(
            "INSERT INTO orchestration_v2_projection_runs VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                extra_run["run_id"],
                "thread1",
                extra_run.get("ordinal", 2),
                "cursor",
                None,
                extra_run.get("status", "completed"),
                extra_run.get("requested_at", "2026-11-03T16:25:00.000Z"),
                extra_run.get("completed_at", "2026-11-03T16:40:00.000Z"),
                json.dumps(
                    {
                        "startedAt": extra_run.get(
                            "started_at", "2026-11-03T16:25:01.000Z"
                        ),
                        "completedAt": extra_run.get(
                            "completed_at", "2026-11-03T16:40:00.000Z"
                        ),
                        "modelSelection": {"instanceId": "cursor", "model": "default"},
                    }
                ),
                "cursor",
            ),
        )
    for run_id in ["run1"] + ([extra_run["run_id"]] if extra_run else []):
        conn.execute(
            "INSERT INTO orchestration_v2_projection_run_attempts VALUES (?,?,?,?)",
            (f"att-{run_id}", "thread1", run_id, "pthread1"),
        )
    run1_turns = [
        {
            "turnTokenUsage": {
                "usageStatus": "complete",
                "inputTokens": 1000,
                "cachedInputTokens": 800,
                "outputTokens": 50,
                "reasoningTokens": 10,
            }
        },
        {
            "turnTokenUsage": {
                "usageStatus": "complete",
                "inputTokens": 2000,
                "cachedInputTokens": 1500,
                "outputTokens": 70,
                "reasoningTokens": 0,
            }
        },
        {
            "turnTokenUsage": {
                "usageStatus": "partial",
                "inputTokens": 999999,
                "outputTokens": 999999,
            }
        },
        {"turnTokenUsage": {"usageStatus": "unavailable"}},
    ]
    for i, payload in enumerate(run1_turns):
        conn.execute(
            "INSERT INTO orchestration_v2_projection_provider_turns VALUES (?,?,?,?,?,?)",
            (f"turn{i}", "thread1", "pthread1", "att-run1", i, json.dumps(payload)),
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
                "input": {"url": "https://example.com?token=sk-secret123456"},
            },
        ),
        (
            "item2",
            "file_change",
            {
                "fileName": file_name,
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
        (
            "item4",
            "command_execution",
            {
                "title": title_cmd
                or "curl -u demo:synthetic-password https://example.com",
                "input": "curl -u demo:synthetic-password https://example.com",
                "startedAt": "2026-11-03T16:04:00.000Z",
                "completedAt": "2026-11-03T16:04:01.000Z",
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


class EmpryoTests(unittest.TestCase):
    def test_turns_order_privacy_and_reconciliation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "threads.db"
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE threads (id TEXT, session_dir TEXT)")
                conn.execute("INSERT INTO threads VALUES (?, ?)", ("thread", str(root)))
            (root / "meta.json").write_text(json.dumps({"id": "thread", "title": "private"}))
            events = [
                {"k": "assistant", "turnId": "turn", "ts": 4000, "status": "complete", "core": "secret"},
                {"k": "tool-end", "turnId": "turn", "ts": 3500, "toolCallId": "call", "output": "secret"},
                {"k": "tool-start", "turnId": "turn", "ts": 3000, "toolCallId": "call", "name": "shell", "args": "secret"},
                {"k": "tool-start", "turnId": "turn", "ts": 3100, "toolCallId": "other", "name": "secret"},
                {"k": "user", "turnId": "turn", "tabId": "tab", "ts": 2000, "core": "secret"},
                {"k": "tab", "tabId": "tab", "ts": 1000, "patch": {"activeModel": "subscriptions/gpt-6.1-terra"}},
            ]
            (root / "session.jsonl").write_text("\n".join(map(json.dumps, events)) + "\n{broken")
            with patch.dict("os.environ", {"EMPRYO_THREADS_DB": str(db)}):
                traces = collect_empryo(since=datetime.fromtimestamp(0, timezone.utc), until=datetime.fromtimestamp(3, timezone.utc))
                self.assertEqual(len(traces), 1)
                trace = traces[0]
                self.assertEqual(trace["duration_ms"], 2000)
                self.assertEqual(trace["tool_calls"], [{"name": "shell", "type": "tool", "duration_ms": 500}, {"name": "other", "type": "tool"}])
                self.assertEqual(trace["tool_call_count"], 2)
                self.assertNotIn("secret", json.dumps(trace))
                self.assertEqual(collect_empryo(run_ids=[trace["run_id"]]), traces)
                self.assertEqual(collect_empryo(since=datetime.fromtimestamp(2, timezone.utc), until=datetime.fromtimestamp(2, timezone.utc)), [])


    def test_terminal_statuses_and_evidence_privacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "threads.db"
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE threads (id TEXT, session_dir TEXT)")
                conn.execute("INSERT INTO threads VALUES (?, ?)", ("thread", str(root)))
            (root / ".git").mkdir()
            (root / "meta.json").write_text(json.dumps({"id": "thread", "cwd": str(root), "title": "MO-124 private"}))
            events = [
                {"k": "tab", "tabId": "t", "ts": 1, "patch": {"activeModel": "proxy/new-model"}},
                {"k": "user", "tabId": "t", "turnId": "a", "ts": 2},
                {"k": "tool-start", "tabId": "t", "turnId": "a", "ts": 3, "toolCallId": "c", "name": "edit_file", "args": {"path": "../private-secret"}},
                {"k": "tool-start", "tabId": "t", "turnId": "a", "ts": 4, "toolCallId": "p", "name": "run_tool", "args": {"name": "computer_preview"}},
                {"k": "assistant", "tabId": "t", "turnId": "a", "ts": 5, "status": "error"},
                {"k": "turn-stop", "tabId": "t", "turnId": "a", "ts": 5},
                {"k": "user", "tabId": "t", "turnId": "b", "ts": 6},
                {"k": "turn-stop", "tabId": "t", "turnId": "b", "ts": 7},
                {"k": "user", "tabId": "t", "turnId": "c", "ts": 8},
                {"k": "user", "tabId": "t", "turnId": "d", "ts": 9},
            ]
            (root / "session.jsonl").write_text("\n".join(map(json.dumps, events)))
            with patch.dict("os.environ", {"EMPRYO_THREADS_DB": str(db)}):
                traces = collect_empryo(since=datetime.fromtimestamp(0, timezone.utc), until=datetime.fromtimestamp(1, timezone.utc))
            self.assertEqual([t["status"] for t in traces], ["failed", "interrupted", "interrupted", "unknown"])
            self.assertEqual(traces[0]["final_state"], "failed")
            self.assertEqual(traces[0]["provider"], "proxy")
            self.assertEqual(traces[0]["task_key"], "MO-124")
            self.assertIsNone(traces[0]["files_outside_worktree"])
            self.assertEqual(traces[0]["preview_or_playwright"], ["preview"])
            self.assertEqual(traces[0]["outcome_evidence"], "unknown")
            self.assertNotIn("private", json.dumps(traces))

    def test_session_cwd_does_not_establish_assigned_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            checkout = base / "checkout"
            checkout.mkdir()
            (checkout / ".git").mkdir()
            worktree = base / ".worktrees" / "checkout" / "assigned"
            worktree.mkdir(parents=True)
            db = base / "threads.db"
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE threads (id TEXT, session_dir TEXT)")
                conn.execute("INSERT INTO threads VALUES (?, ?)", ("thread", str(base)))
            (base / "meta.json").write_text(json.dumps({"id": "thread", "cwd": str(checkout)}))
            events = [
                {"k": "user", "tabId": "t", "turnId": "a", "ts": 1},
                {"k": "tool-start", "turnId": "a", "ts": 2, "toolCallId": "1", "name": "edit_file", "args": {"path": str(worktree / "file.py")}},
                {"k": "tool-start", "turnId": "a", "ts": 3, "toolCallId": "2", "name": "edit_file", "args": {"path": "in-checkout.py"}},
            ]
            (base / "session.jsonl").write_text("\n".join(map(json.dumps, events)))
            with patch.dict("os.environ", {"EMPRYO_THREADS_DB": str(db)}):
                trace = collect_empryo(since=datetime.fromtimestamp(0, timezone.utc), until=datetime.fromtimestamp(1, timezone.utc))[0]
            self.assertIsNone(trace["files_outside_worktree"])
            self.assertNotIn("files_outside_worktree", score_trace(trace)["flags"])
            self.assertEqual(trace["tool_call_count"], 2)


class ScrubTests(unittest.TestCase):
    def test_redacts_keys_home_phone_ssn_basic_auth(self):
        s = scrub_string(
            "key=phc_abc123 token=sk-ant-xyz email me@example.com "
            "/Users/shyamsivakumar/Code/x call 415-555-1212 ssn 123-45-6789 "
            "curl -u demo:synthetic-password https://x "
            "Authorization: Basic dXNlcjpwYXNz"
        )
        self.assertNotIn("phc_abc123", s)
        self.assertNotIn("sk-ant-xyz", s)
        self.assertNotIn("me@example.com", s)
        self.assertNotIn("415-555-1212", s)
        self.assertNotIn("123-45-6789", s)
        self.assertNotIn("demo:synthetic-password", s)
        self.assertNotIn("dXNlcjpwYXNz", s)
        self.assertNotIn("YTpi", scrub_string("Basic YTpi"))
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


class PathAndToolTests(unittest.TestCase):
    def test_tool_name_never_command_text(self):
        name = _tool_name(
            "command_execution",
            {"title": "curl -u demo:synthetic-password https://x", "input": "secret"},
        )
        self.assertEqual(name, "command_execution")

    def test_path_traversal_rejected(self):
        root = "/repo/wt"
        self.assertFalse(_path_under("/repo/wt/../../other/file.py", root))
        self.assertTrue(_path_under("/repo/wt/src/a.py", root))

    def test_sibling_worktree_not_auto_allowed(self):
        roots = _allowed_roots(
            "/Users/x/.t3/worktrees/mac-ops/t3-abc",
            "/Users/x/Code/mac-ops",
        )
        self.assertEqual(
            roots,
            [
                "/Users/x/.t3/worktrees/mac-ops/t3-abc",
                "/Users/x/Code/mac-ops",
            ],
        )
        self.assertFalse(
            any(
                _path_under("/Users/x/.t3/worktrees/mac-ops/t3-other/file.py", r)
                for r in roots
            )
        )

    def test_post_run_merge_not_credited(self):
        payload = {
            "pullRequests": [
                {
                    "url": "https://github.com/o/r/pull/1",
                    "repository": "o/r",
                    "number": 1,
                    "snapshot": {
                        "state": "merged",
                        "mergedAt": "2026-11-03T16:30:00Z",
                        "checksState": "passing",
                    },
                }
            ]
        }
        prs, evidence = _pr_outcomes_for_run(
            payload, completed_at="2026-11-03T16:20:00Z", status="completed"
        )
        self.assertEqual(evidence, "known")
        self.assertEqual(prs[0]["state"], "open")
        self.assertEqual(prs[0]["timing"], "post_run_merge")


class CollectEvalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "state.sqlite"
        # Merge before run end so proof can credit when appropriate.
        _make_db(self.db, merged_at="2026-11-03T16:15:00Z")

    def tearDown(self):
        self.tmp.cleanup()

    def test_collect_builds_trace_without_command_secrets(self):
        traces = collect_runs(
            since=datetime(2026, 11, 3, tzinfo=timezone.utc),
            until=datetime(2026, 11, 4, tzinfo=timezone.utc),
            db_path=self.db,
        )
        self.assertEqual(len(traces), 1)
        t = traces[0]
        self.assertEqual(t["task_key"], "MO-124")
        self.assertEqual(t["tool_call_count"], 4)
        names = [c["name"] for c in t["tool_calls"]]
        self.assertIn("command_execution", names)
        self.assertTrue(all("synthetic-password" not in n for n in names))
        blob = json.dumps(t)
        self.assertNotIn("sk-secret", blob)
        self.assertNotIn("synthetic-password", blob)
        self.assertEqual(t["pull_requests"][0]["state"], "merged")

    def test_tokens_sum_complete_turns_and_survive_scrub(self):
        db = self.root / "tokens.sqlite"
        _make_db(
            db,
            extra_run={"run_id": "run2", "ordinal": 2},
        )
        traces = collect_runs(
            since=datetime(2026, 11, 3, tzinfo=timezone.utc),
            until=datetime(2026, 11, 4, tzinfo=timezone.utc),
            db_path=db,
        )
        by_id = {t["run_id"]: t for t in traces}
        self.assertEqual(
            by_id["run1"]["tokens"],
            {
                "inputTokens": 3000,
                "cachedInputTokens": 2300,
                "outputTokens": 120,
                "reasoningTokens": 10,
                "totalTokens": 3120,
                "turnsComplete": 2,
                "turnsPartial": 1,
                "turnsUnavailable": 1,
            },
        )
        self.assertIsNone(by_id["run1"]["cost_usd"])
        self.assertIsNone(by_id["run2"]["tokens"])
        stored = json.loads(write_trace(by_id["run1"], root=self.root).read_text())
        self.assertEqual(stored["tokens"], by_id["run1"]["tokens"])

    def test_store_and_eval_proof(self):
        traces = collect_runs(
            since=datetime(2026, 11, 3, tzinfo=timezone.utc),
            until=datetime(2026, 11, 4, tzinfo=timezone.utc),
            db_path=self.db,
        )
        write_trace(traces[0], root=self.root)
        scored = score_trace(traces[0])
        self.assertTrue(scored["merged_pr"])
        # syncedAt before run end → CI known → proven
        self.assertTrue(scored["claimed_done_with_proof"])
        self.assertEqual(scored["proof_status"], "proven")
        self.assertIn("files_outside_worktree", scored["flags"])
        self.assertIn("preview_or_playwright", scored["flags"])
        summary = evaluate_day("2026-11-03", root=self.root)
        self.assertEqual(summary["merged_pr_count"], 1)
        self.assertEqual(summary["claimed_done_with_proof"], 1)

    def test_later_snapshot_ci_does_not_disprove(self):
        db = self.root / "late.sqlite"
        _make_db(
            db,
            merged_at="2026-11-03T16:10:00Z",
            completed_at="2026-11-03T16:20:00.000Z",
            checks="failing",
            synced_at="2026-11-03T18:00:00Z",
        )
        traces = collect_runs(
            since=datetime(2026, 11, 3, tzinfo=timezone.utc),
            until=datetime(2026, 11, 4, tzinfo=timezone.utc),
            db_path=db,
        )
        scored = score_trace(traces[0])
        self.assertTrue(scored["merged_pr"])
        self.assertIsNone(traces[0]["pull_requests"][0]["checks_state"])
        self.assertEqual(scored["proof_status"], "missing")
        self.assertNotIn("claimed_done_without_proof", scored["flags"])

    def test_cross_day_pr_contributions(self):
        prior = {
            "merged_pr": False,
            "duration_ms": 2000,
            "cost_usd": 2.0,
            "tokens_total": 500,
            "pull_requests": [
                {
                    "repository": "o/r",
                    "number": 1,
                    "state": "open",
                    "timing": "post_run_merge",
                }
            ],
        }
        merge_day = {
            "merged_pr": True,
            "duration_ms": 1000,
            "cost_usd": 1.0,
            "tokens_total": 250,
            "pull_requests": [
                {
                    "repository": "o/r",
                    "number": 1,
                    "state": "merged",
                    "merged_at": "t",
                    "timing": "known",
                    "merge_by_end": True,
                }
            ],
        }
        metrics = _merged_pr_metrics([merge_day], contribution_rows=[prior, merge_day])
        self.assertEqual(metrics["distinct_merged_prs"], 1)
        self.assertEqual(metrics["time_per_merged_pr_ms"]["total"], 3000)
        self.assertEqual(metrics["cost_per_merged_pr_usd"]["total"], 3.0)
        self.assertEqual(metrics["tokens_per_merged_pr"]["total"], 750)
        # Prior day alone still has zero merged PRs.
        prior_only = _merged_pr_metrics([prior], contribution_rows=[prior, merge_day])
        self.assertEqual(prior_only["distinct_merged_prs"], 0)

    def test_post_run_merge_and_interrupted_not_proven(self):
        db = self.root / "post.sqlite"
        _make_db(
            db,
            merged_at="2026-11-03T16:30:00Z",
            status="interrupted",
            completed_at="2026-11-03T16:20:00.000Z",
        )
        traces = collect_runs(
            since=datetime(2026, 11, 3, tzinfo=timezone.utc),
            until=datetime(2026, 11, 4, tzinfo=timezone.utc),
            db_path=db,
        )
        scored = score_trace(traces[0])
        self.assertFalse(scored["merged_pr"])
        self.assertFalse(scored["claimed_done_with_proof"])
        self.assertEqual(scored["proof_status"], "n/a")

    def test_missing_proof_when_no_pr(self):
        trace = {
            "status": "completed",
            "pull_requests": [],
            "outcome_evidence": "known",
            "named_blocker": None,
            "files_outside_worktree": [],
            "preview_or_playwright": [],
        }
        scored = score_trace(trace)
        self.assertEqual(scored["proof_status"], "missing")
        self.assertIn("missing_proof", scored["flags"])

    def test_distinct_pr_metrics(self):
        db = self.root / "dup.sqlite"
        _make_db(
            db,
            merged_at="2026-11-03T16:15:00Z",
            extra_run={
                "run_id": "run2",
                "ordinal": 2,
                "requested_at": "2026-11-03T16:25:00.000Z",
                "started_at": "2026-11-03T16:25:01.000Z",
                "completed_at": "2026-11-03T16:35:00.000Z",
            },
        )
        traces = collect_runs(
            since=datetime(2026, 11, 3, tzinfo=timezone.utc),
            until=datetime(2026, 11, 4, tzinfo=timezone.utc),
            db_path=db,
        )
        for t in traces:
            write_trace(t, root=self.root)
        summary = evaluate_day("2026-11-03", root=self.root)
        self.assertEqual(summary["merged_pr_count"], 1)
        self.assertEqual(summary["merged_pr_run_count"], 2)
        self.assertEqual(summary["time_per_merged_pr_ms"]["count"], 1)

    def test_posthog_dry_run_and_skip(self):
        self.assertEqual(
            export_posthog([{"run_id": "r"}], api_key=None)["skipped"], "no_api_key"
        )
        out = export_posthog(
            [{"run_id": "r", "thread_id": "t"}], api_key="phc_test", dry_run=True
        )
        self.assertEqual(out["exported"], 1)
        self.assertTrue(out["dry_run"])

    def test_dst_day_boundary(self):
        # 2026-11-01 is DST end in America/Los_Angeles (falls back).
        start, end, day = _parse_day("2026-11-01")
        self.assertEqual(day, "2026-11-01")
        local = ZoneInfo("America/Los_Angeles")
        self.assertEqual(start.astimezone(local).hour, 0)
        self.assertEqual(end.astimezone(local).hour, 0)
        self.assertEqual((end - start).total_seconds(), 25 * 3600)

    def test_post_run_merge_strips_ci_for_scoring(self):
        prs, _ = _pr_outcomes_for_run(
            {
                "pullRequests": [
                    {
                        "url": "https://github.com/o/r/pull/1",
                        "repository": "o/r",
                        "number": 1,
                        "snapshot": {
                            "state": "merged",
                            "mergedAt": "2026-11-03T16:30:00Z",
                            "checksState": "failing",
                            "reviewDecision": "CHANGES_REQUESTED",
                        },
                    }
                ]
            },
            completed_at="2026-11-03T16:20:00Z",
            status="interrupted",
        )
        self.assertIsNone(prs[0]["checks_state"])
        self.assertIsNone(prs[0]["review_decision"])
        scored = score_trace(
            {
                "status": "interrupted",
                "pull_requests": prs,
                "outcome_evidence": "known",
                "named_blocker": None,
                "files_outside_worktree": [],
                "preview_or_playwright": [],
            }
        )
        self.assertNotIn("stopped_while_green", scored["flags"])
        self.assertNotIn("claimed_done_without_proof", scored["flags"])

    def test_same_pr_proof_required(self):
        scored = score_trace(
            {
                "status": "completed",
                "outcome_evidence": "known",
                "named_blocker": None,
                "files_outside_worktree": [],
                "preview_or_playwright": [],
                "pull_requests": [
                    {
                        "repository": "o/r",
                        "number": 1,
                        "state": "merged",
                        "merged_at": "t",
                        "timing": "known",
                        "evidence_by_end": True,
                        "checks_state": "pending",
                        "review_decision": None,
                    },
                    {
                        "repository": "o/r",
                        "number": 2,
                        "state": "open",
                        "timing": "known",
                        "evidence_by_end": True,
                        "checks_state": "passing",
                        "review_decision": None,
                    },
                ],
            }
        )
        self.assertEqual(scored["proof_status"], "missing")
        self.assertFalse(scored["claimed_done_with_proof"])

    def test_pre_merge_runs_count_toward_pr_totals(self):
        rows = [
            {
                "merged_pr": False,
                "duration_ms": 1000,
                "cost_usd": 1.0,
                "pull_requests": [
                    {
                        "repository": "o/r",
                        "number": 1,
                        "state": "open",
                        "timing": "post_run_merge",
                    }
                ],
            },
            {
                "merged_pr": True,
                "duration_ms": 1000,
                "cost_usd": 1.0,
                "pull_requests": [
                    {
                        "repository": "o/r",
                        "number": 1,
                        "state": "merged",
                        "merged_at": "t",
                        "timing": "known",
                    }
                ],
            },
        ]
        metrics = _merged_pr_metrics(rows)
        self.assertEqual(metrics["distinct_merged_prs"], 1)
        self.assertEqual(metrics["time_per_merged_pr_ms"]["total"], 2000)
        self.assertEqual(metrics["cost_per_merged_pr_usd"]["total"], 2.0)


if __name__ == "__main__":
    unittest.main()
