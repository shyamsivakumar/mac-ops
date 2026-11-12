"""Unit tests for session traces collected from T3 Code (no live T3 needed).

The fixture is a fake ``t3mcp`` caller that answers ``t3_thread_list`` and
``t3_thread_read`` from in-memory thread records and is passed to
``collect_runs`` as ``t3_call``.  Every string in the fixture is synthetic: the
sentinels below must never survive collection, and no real secret is used
anywhere.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from session_traces.__main__ import _parse_day
from session_traces.collect import (
    collect_runs,
)
from session_traces.eval_day import _merged_pr_metrics, evaluate_day, score_trace
from session_traces.scrub import scrub_path, scrub_string, scrub_trace
from session_traces.store import export_posthog, write_trace


USER_SENTINEL = "SYNTHETIC-USER-SENTINEL"
ASSISTANT_SENTINEL = "SYNTHETIC-ASSISTANT-SENTINEL"
ALL_SENTINELS = (USER_SENTINEL, ASSISTANT_SENTINEL)

TASK_UUID = "11111111-2222-3333-4444-555555555555"
TASK_THREAD_ID = f"mcp:{TASK_UUID}"
TASK_RUN_1 = f"run:thread:{TASK_THREAD_ID}:ordinal:1"
TASK_RUN_2 = f"run:thread:{TASK_THREAD_ID}:ordinal:2"
REVIEW_UUID = "99999999-8888-7777-6666-555555555555"
REVIEW_THREAD_ID = f"mcp:{REVIEW_UUID}"
REVIEW_RUN_1 = f"run:thread:{REVIEW_THREAD_ID}:ordinal:1"
PROJECT_ID = "mcp:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
TASK_MODEL = "gpt-6.1-terra"
REQUESTED_MODEL = "claude-opus-5-5"
REVIEW_MODEL = "claude-opus-5-5"
WINDOW_SINCE = datetime(2026, 11, 3, tzinfo=timezone.utc)
WINDOW_UNTIL = datetime(2026, 11, 4, tzinfo=timezone.utc)


def _run(
    run_id: str,
    *,
    ordinal: int = 1,
    status: str = "completed",
    started_at: str = "2026-11-03T16:00:01.000Z",
    completed_at: str = "2026-11-03T16:20:00.000Z",
    model: str = TASK_MODEL,
    executed_model: str | None = None,
    provider: str = "codex",
) -> dict:
    return {
        "runId": run_id,
        "ordinal": ordinal,
        "status": status,
        "providerInstanceId": provider,
        "model": model,
        "executedModel": executed_model or model,
        "requestedAt": started_at,
        "startedAt": started_at,
        "completedAt": completed_at,
    }


def _pull_request(number: int = 99, state: str = "merged") -> dict:
    return {
        "host": "github.com",
        "repository": "shyamsivakumar/mac-ops",
        "number": number,
        "url": f"https://github.com/shyamsivakumar/mac-ops/pull/{number}",
        "source": "linked",
        "state": state,
    }


class FakeT3:
    """Answers the two read-only t3mcp tools the collector calls."""

    def __init__(self, threads: list[dict], messages: dict[str, list[dict]]):
        self.threads = {t["threadId"]: t for t in threads}
        self.messages = messages
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, tool: str, args: dict) -> dict:
        self.calls.append((tool, args))
        if tool == "t3_thread_list":
            rows = sorted(self.threads.values(), key=lambda t: t["updatedAt"], reverse=True)
            cursor, limit = args.get("cursor", 0), args["limit"]
            page = rows[cursor : cursor + limit]
            nxt = cursor + len(page)
            summary = [{k: v for k, v in t.items() if k != "runs"} for t in page]
            return {"threads": summary, "total": len(rows), "nextCursor": nxt if nxt < len(rows) else None}
        if tool == "t3_thread_read":
            thread = self.threads[args["threadId"]]
            body = {"thread": {k: v for k, v in thread.items() if k != "runs"}, "recentRuns": thread["runs"]}
            if args.get("view") == "messages":
                items = self.messages.get(thread["threadId"], [])
                after = args.get("afterPosition", 0)
                page = [i for i in items if i["position"] >= after][: args["limit"]]
                more = len(page) < len([i for i in items if i["position"] >= after])
                body.update({"items": page, "hasMore": more, "nextPosition": page[-1]["position"] + 1 if page else after})
            else:
                body["items"] = []
            return body
        raise AssertionError(f"unexpected tool {tool}")


def _thread(thread_id: str, *, title: str, project_id: str, runs: list[dict], pull_requests: list[dict], provider: str) -> dict:
    return {
        "threadId": thread_id,
        "projectId": project_id,
        "title": title,
        "status": runs[-1]["status"],
        "providerInstanceId": provider,
        "pullRequests": pull_requests,
        "linkedPullRequest": pull_requests[0] if pull_requests else None,
        "parentThreadId": None,
        "relationshipToParent": None,
        "archived": False,
        "settled": True,
        "createdAt": runs[0]["startedAt"],
        "updatedAt": runs[-1]["completedAt"],
        "runs": runs,
    }


def _task_messages(runs: list[dict]) -> list[dict]:
    items = []
    for n, run in enumerate(runs):
        items.append({"position": 2 * n, "runId": run["runId"], "type": "user_message", "text": f"{USER_SENTINEL}: work the ticket"})
        items.append({"position": 2 * n + 1, "runId": run["runId"], "type": "assistant_message", "text": f"{ASSISTANT_SENTINEL} done"})
    return items


def _review_messages(verdict_line: str | None, run_id: str) -> list[dict]:
    report = f"{ASSISTANT_SENTINEL}\n\nchecked the change\n"
    if verdict_line:
        report += f"\n{verdict_line}\n"
    return [
        {"position": 0, "runId": run_id, "type": "user_message", "text": f"{USER_SENTINEL}: review the change"},
        {"position": 1, "runId": run_id, "type": "assistant_message", "text": report},
    ]


def _build_hub(
    root: Path,
    *,
    runs: list[dict] | None = None,
    pull_requests: list[dict] | None = None,
    task_title: str = "MO-124 · session traces",
    review: bool = True,
    review_verdict: str | None = "VERDICT: PASS",
    review_model: str = REVIEW_MODEL,
    review_title: str = "MO-124 · review of session traces",
    review_project_id: str = PROJECT_ID,
    review_run_times: tuple[str, str] = (
        "2026-11-03T16:25:00.000Z",
        "2026-11-03T16:35:00.000Z",
    ),
) -> FakeT3:
    """A fake T3 holding one task thread and, optionally, its review thread."""
    if runs is None:
        runs = [_run(TASK_RUN_1, model=REQUESTED_MODEL, executed_model=TASK_MODEL)]
    if pull_requests is None:
        pull_requests = [_pull_request()]
    threads = [_thread(TASK_THREAD_ID, title=task_title, project_id=PROJECT_ID, runs=runs, pull_requests=pull_requests, provider="codex")]
    messages = {TASK_THREAD_ID: _task_messages(runs)}
    if review:
        review_run = _run(REVIEW_RUN_1, started_at=review_run_times[0], completed_at=review_run_times[1], model=review_model, provider="claudeAgent")
        threads.append(_thread(REVIEW_THREAD_ID, title=review_title, project_id=review_project_id, runs=[review_run], pull_requests=[], provider="claudeAgent"))
        messages[REVIEW_THREAD_ID] = _review_messages(review_verdict, review_run["runId"])
    return FakeT3(threads, messages)


class ScrubTests(unittest.TestCase):
    def test_redacts_keys_home_phone_ssn_basic_auth(self):
        s = scrub_string(
            "key=phc_abc123 token=sk-EXAMPLE email me@example.com "
            "/Users/shyamsivakumar/Code/x call 415-555-1212 ssn 123-45-6789 "
            "curl -u exam:passwordxxxxxxxxxx https://x "
            "Authorization: Basic dXNlcjpwYXNz"
        )
        self.assertNotIn("phc_abc123", s)
        self.assertNotIn("sk-EXAMPLE", s)
        self.assertNotIn("me@example.com", s)
        self.assertNotIn("415-555-1212", s)
        self.assertNotIn("123-45-6789", s)
        self.assertNotIn("exam:passwordxxxxxxxxxx", s)
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


class CollectEvalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # Merge before run end so the merge can be credited when appropriate.
        self.hub = _build_hub(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _collect(self, hub: FakeT3 | None = None):
        return collect_runs(
            since=WINDOW_SINCE,
            until=WINDOW_UNTIL,
            t3_call=hub or self.hub,
        )

    def _task_trace(self, traces: list[dict]) -> dict:
        matches = [t for t in traces if t.get("thread_id") == TASK_THREAD_ID]
        self.assertEqual(len(matches), 1, "expected exactly one task-EXAMPL trace")
        return matches[0]

    def test_collect_builds_trace_without_text(self):
        traces = self._collect()
        task = self._task_trace(traces)
        self.assertEqual(task["task_key"], "MO-124")
        self.assertEqual(task["source"], "t3")
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["model"], TASK_MODEL)
        blob = json.dumps(task)
        for sentinel in ALL_SENTINELS:
            self.assertNotIn(sentinel, blob)
        self.assertEqual(task["pull_requests"][0]["number"], 99)
        self.assertEqual(task["duration_ms"], 1199000)

    def test_fields_t3_cannot_supply_are_not_collected(self):
        task = self._task_trace(self._collect())
        for key in ("tool_calls", "tool_call_count", "tokens", "cost_usd", "stop_reason", "task_type", "worktree_path", "branch"):
            self.assertIsNone(task[key], key)
        pr = task["pull_requests"][0]
        self.assertIsNone(pr["merged_at"])
        self.assertIsNone(pr["checks_state"])

    def test_fallback_is_per_run_from_run_records(self):
        hub = _build_hub(
            self.root / "fallback",
            runs=[
                _run(TASK_RUN_1, model=REQUESTED_MODEL),
                _run(
                    TASK_RUN_2,
                    ordinal=2,
                    started_at="2026-11-03T16:20:00.000Z",
                    completed_at="2026-11-03T16:30:00.000Z",
                    model=REQUESTED_MODEL,
                    executed_model=TASK_MODEL,
                ),
            ],
        )
        by_run = {t["run_id"]: t for t in self._collect(hub) if t["thread_id"] == TASK_THREAD_ID}
        same_model = by_run[TASK_RUN_1]
        self.assertFalse(same_model["model_fallback"])
        self.assertEqual(same_model["model"], REQUESTED_MODEL)
        fell_back = by_run[TASK_RUN_2]
        self.assertTrue(fell_back["model_fallback"])
        self.assertEqual(fell_back["model"], TASK_MODEL)
        self.assertEqual(fell_back["requested_model"], REQUESTED_MODEL)
        self.assertEqual(fell_back["base_model"], REQUESTED_MODEL)
        self.assertEqual(fell_back["fallback_model"], TASK_MODEL)

    def test_thread_list_excludes_subagents_and_reads_no_write_tool(self):
        self._collect()
        listed = [args for tool, args in self.hub.calls if tool == "t3_thread_list"]
        self.assertTrue(listed and all(args["includeSubagents"] is False for args in listed))
        self.assertEqual({tool for tool, _ in self.hub.calls}, {"t3_thread_list", "t3_thread_read"})

    def test_stored_trace_keeps_no_sentinels_or_text(self):
        traces = self._collect()
        task = self._task_trace(traces)
        path = write_trace(task, root=self.root)
        stored = path.read_text(encoding="utf-8")
        for sentinel in ALL_SENTINELS:
            self.assertNotIn(sentinel, stored)
        obj = json.loads(stored)
        self.assertNotIn("text", obj)
        self.assertNotIn("prompt", obj)
        self.assertEqual(obj["run_id"], task["run_id"])

    def test_store_and_eval_proof(self):
        traces = self._collect()
        task = self._task_trace(traces)
        write_trace(task, root=self.root)
        scored = score_trace(task)
        # T3 reports a merged PR but no merge time: the merge is not credited.
        self.assertFalse(scored["merged_pr"])
        # T3 has no CI snapshot: never claim proof we cannot see.
        self.assertEqual(scored["proof_status"], "missing")
        self.assertFalse(scored["claimed_done_with_proof"])
        self.assertNotIn("claimed_done_without_proof", scored["flags"])
        summary = evaluate_day("2026-11-03", root=self.root)
        self.assertEqual(summary["merged_pr_count"], 0)
        self.assertEqual(summary["claimed_done_with_proof"], 0)

    def test_cross_day_pr_contributions(self):
        prior = {
            "merged_pr": False,
            "duration_ms": 2000,
            "cost_usd": 2.0,
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
        # Prior day alone still has zero merged PRs.
        prior_only = _merged_pr_metrics([prior], contribution_rows=[prior, merge_day])
        self.assertEqual(prior_only["distinct_merged_prs"], 0)

    def test_merged_pr_with_unknown_timing_is_not_proven(self):
        hub = _build_hub(self.root / "interrupted", runs=[_run(TASK_RUN_1, status="interrupted")])
        task = self._task_trace(self._collect(hub))
        scored = score_trace(task)
        self.assertFalse(scored["merged_pr"])
        self.assertFalse(scored["claimed_done_with_proof"])
        self.assertEqual(task["pull_requests"][0]["timing"], "unknown")
        self.assertEqual(task["pull_requests"][0]["state"], "merged_unknown_timing")

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

    def test_flags_for_outside_files_and_preview(self):
        scored = score_trace(
            {
                "status": "completed",
                "outcome_evidence": "known",
                "named_blocker": None,
                "files_outside_worktree": ["/Users/[user]/Code/other-repo/secret.env"],
                "preview_or_playwright": ["html_preview"],
                "pull_requests": [],
            }
        )
        self.assertIn("files_outside_worktree", scored["flags"])
        self.assertIn("preview_or_playwright", scored["flags"])

    def test_proof_requires_known_green_ci(self):
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
                        "checks_state": "passing",
                        "review_decision": None,
                    }
                ],
            }
        )
        self.assertTrue(scored["merged_pr"])
        self.assertEqual(scored["proof_status"], "proven")
        self.assertTrue(scored["claimed_done_with_proof"])


class ReviewVerdictTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _task_trace(self, hub: FakeT3) -> dict:
        traces = collect_runs(
            since=WINDOW_SINCE,
            until=WINDOW_UNTIL,
            t3_call=hub,
        )
        matches = [t for t in traces if t.get("thread_id") == TASK_THREAD_ID]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_review_verdict_pass_and_model(self):
        hub = _build_hub(self.root, review_verdict="VERDICT: PASS")
        task = self._task_trace(hub)
        self.assertEqual(task.get("review_verdict"), "PASS")
        self.assertIn("claude-opus-5-5", str(task.get("review_model")))
        # Only the verdict token is kept: the report text is dropped.
        blob = json.dumps(task)
        self.assertNotIn(ASSISTANT_SENTINEL, blob)
        self.assertNotIn("VERDICT: PASS", blob)

    def test_review_after_the_run_is_not_historical_proof(self):
        hub = _build_hub(self.root, review_verdict="VERDICT: PASS")
        task = self._task_trace(hub)
        self.assertEqual(task.get("review_verdict"), "PASS")
        # The review finished after the task run ended: not proof of anything yet.
        self.assertFalse(task.get("review_evidence_by_end"))

    def test_review_before_the_run_end_is_evidence_by_end(self):
        hub = _build_hub(
            self.root,
            review_verdict="VERDICT: PASS",
            review_run_times=(
                "2026-11-03T16:05:00.000Z",
                "2026-11-03T16:10:00.000Z",
            ),
        )
        task = self._task_trace(hub)
        self.assertEqual(task.get("review_verdict"), "PASS")
        self.assertTrue(task.get("review_evidence_by_end"))
        self.assertEqual(task.get("review_thread_id"), REVIEW_THREAD_ID)
        self.assertEqual(task.get("review_run_id"), REVIEW_RUN_1)
        self.assertEqual(task.get("review_completed_at"), "2026-11-03T16:10:00.000Z")

    def test_review_verdict_fail(self):
        hub = _build_hub(self.root, review_verdict="VERDICT: FAIL")
        task = self._task_trace(hub)
        self.assertEqual(task.get("review_verdict"), "FAIL")
        self.assertNotIn(ASSISTANT_SENTINEL, json.dumps(task))

    def test_review_verdict_unknown_without_verdict_line(self):
        hub = _build_hub(self.root, review_verdict=None)
        task = self._task_trace(hub)
        self.assertNotIn(task.get("review_verdict"), {"PASS", "FAIL"})

    def test_review_from_other_project_is_not_credited(self):
        hub = _build_hub(
            self.root,
            review_verdict="VERDICT: PASS",
            review_project_id="proj:ffffffff-0000-0000-0000-000000000009",
        )
        task = self._task_trace(hub)
        self.assertNotIn(task.get("review_verdict"), {"PASS", "FAIL"})


if __name__ == "__main__":
    unittest.main()
