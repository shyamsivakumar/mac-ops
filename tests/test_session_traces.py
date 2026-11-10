"""Unit tests for session traces collected from the Empryo hub (no live hub needed).

The fixture writes a synthetic ``~/.empryo-hub`` tree (``threads.json``,
``hub.log`` and ``transcripts/*.jsonl``) and points ``collect_runs`` at it via
``hub_path``.  Every string in the fixture is synthetic: the sentinels below
must never survive collection, and no real secret is used anywhere.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from session_traces.__main__ import _parse_day
from session_traces.collect import (
    _allowed_roots,
    _path_under,
    _tool_name,
    collect_runs,
)
from session_traces.eval_day import _merged_pr_metrics, evaluate_day, score_trace
from session_traces.scrub import scrub_path, scrub_string, scrub_trace
from session_traces.store import export_posthog, write_trace

from session_traces.collect import _pr_outcomes_for_run


# Synthetic sentinels: fake strings that must never reach a stored trace.
USER_SENTINEL = "SYNTHETIC-USER-SENTINEL"
COMMAND_SENTINEL = "SYNTHETIC-COMMAND-SENTINEL"
TOOL_TITLE_SENTINEL = "SYNTHETIC-TOOL-TITLE-SENTINEL"
ASSISTANT_SENTINEL = "SYNTHETIC-ASSISTANT-SENTINEL"
ALL_SENTINELS = (
    USER_SENTINEL,
    COMMAND_SENTINEL,
    TOOL_TITLE_SENTINEL,
    ASSISTANT_SENTINEL,
)

TASK_UUID = "11111111-2222-3333-4444-555555555555"
TASK_THREAD_ID = f"emp:{TASK_UUID}"
TASK_RUN_1 = f"run:{TASK_THREAD_ID}:ordinal:1"
TASK_RUN_2 = f"run:{TASK_THREAD_ID}:ordinal:2"
REVIEW_UUID = "99999999-8888-7777-6666-555555555555"
REVIEW_THREAD_ID = f"emp:{REVIEW_UUID}"
REVIEW_RUN_1 = f"run:{REVIEW_THREAD_ID}:ordinal:1"
PROJECT_ID = "proj:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
WORKTREE = "/Users/shyamsivakumar/.empryo-hub/worktrees/mac-ops/mo-124-session-traces"
TASK_MODEL = "subscriptions/gpt-6.1-terra"
REVIEW_MODEL = "subscriptions/claude-opus-5-5"
WINDOW_SINCE = datetime(2026, 11, 3, tzinfo=timezone.utc)
WINDOW_UNTIL = datetime(2026, 11, 4, tzinfo=timezone.utc)
# hub.log stamps are local wall-clock; the collector converts them to UTC.
HUB_LOCAL_TZ = ZoneInfo("America/Los_Angeles")


def _hub_stamp(iso_utc: str) -> str:
    return (
        _iso(iso_utc).astimezone(HUB_LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")
    )


def _iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _shift(value: str, seconds: int) -> str:
    return (_iso(value) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _transcript_name(thread_id: str) -> str:
    """Mirror emp-hub's transcript file naming."""
    slug = re.sub(r"[^a-z0-9]+", "-", thread_id.lower()).strip("-")[:48] or "thread"
    return f"{slug}-{thread_id.split(':')[-1][:8]}.jsonl"


def _run(
    run_id: str,
    *,
    ordinal: int = 1,
    status: str = "completed",
    started_at: str = "2026-11-03T16:00:01.000Z",
    completed_at: str = "2026-11-03T16:20:00.000Z",
    stop_reason: str = "end_turn",
    cost_usd: float = 0.25,
    steps: int = 3,
) -> dict:
    return {
        "runId": run_id,
        "ordinal": ordinal,
        "status": status,
        "startedAt": started_at,
        "completedAt": completed_at,
        "stopReason": stop_reason,
        "usage": {
            "tokens": {
                "input": 1200,
                "output": 340,
                "cachedRead": 100,
                "cachedWrite": 0,
            },
            "costUsd": cost_usd,
            "steps": steps,
        },
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


def _tool_entries(started_at: str) -> list[dict]:
    """Three tool calls inside one run (no text, no secrets kept by design)."""
    return [
        {
            "type": "dynamic_tool",
            "toolKind": "other",
            "status": "completed",
            "title": "Code script",
            "createdAt": _shift(started_at, 60),
        },
        {
            "type": "command_execution",
            "toolKind": "execute",
            "status": "completed",
            "title": f"echo {COMMAND_SENTINEL}",
            "createdAt": _shift(started_at, 120),
        },
        {
            "type": "dynamic_tool",
            "toolKind": "read",
            "status": "completed",
            "title": f"Read {TOOL_TITLE_SENTINEL}",
            "createdAt": _shift(started_at, 180),
        },
    ]


def _task_transcript(runs: list[dict]) -> list[dict]:
    entries: list[dict] = []
    position = 0
    for run in runs:
        position += 1
        entries.append(
            {
                "id": f"item:{TASK_THREAD_ID}:{position}",
                "position": position,
                "createdAt": run["startedAt"],
                "type": "user_message",
                "status": "completed",
                "text": f"{USER_SENTINEL}: work the ticket",
            }
        )
        for tool in _tool_entries(run["startedAt"]):
            position += 1
            entries.append(
                {
                    "id": f"item:{TASK_THREAD_ID}:{position}",
                    "position": position,
                    "createdAt": tool["createdAt"],
                    "type": tool["type"],
                    "toolKind": tool["toolKind"],
                    "status": tool["status"],
                    "title": tool["title"],
                }
            )
        position += 1
        entries.append(
            {
                "id": f"item:{TASK_THREAD_ID}:{position}",
                "position": position,
                "createdAt": run["completedAt"],
                "type": "run_finished",
                "status": "completed",
                "stopReason": run.get("stopReason"),
                "usage": run.get("usage"),
            }
        )
    return entries


def _review_transcript(
    verdict_line: str | None,
    *,
    started_at: str = "2026-11-03T16:25:00.000Z",
    completed_at: str = "2026-11-03T16:35:00.000Z",
) -> list[dict]:
    """A review thread whose last assistant report ends with the VERDICT line."""
    report = f"{ASSISTANT_SENTINEL}\n\nchecked the change\n"
    if verdict_line:
        report += f"\n{verdict_line}\n"
    return [
        {
            "id": f"item:{REVIEW_THREAD_ID}:1",
            "position": 1,
            "createdAt": started_at,
            "type": "user_message",
            "status": "completed",
            "text": f"{USER_SENTINEL}: review the change",
        },
        {
            "id": f"item:{REVIEW_THREAD_ID}:2",
            "position": 2,
            "createdAt": _shift(completed_at, -60),
            "type": "assistant_message",
            "status": "completed",
            "text": report,
        },
        {
            "id": f"item:{REVIEW_THREAD_ID}:3",
            "position": 3,
            "createdAt": completed_at,
            "type": "run_finished",
            "status": "completed",
            "stopReason": "end_turn",
            "usage": {
                "tokens": {"input": 900, "output": 120, "cachedRead": 0, "cachedWrite": 0},
                "costUsd": 0.1,
                "steps": 2,
            },
        },
    ]


def _review_thread(
    *,
    title: str,
    model: str,
    project_id: str,
    run: dict,
) -> dict:
    return {
        "threadId": REVIEW_THREAD_ID,
        "projectId": project_id,
        "title": title,
        "createdBy": "agent",
        "creationSource": "mcp",
        "status": "completed",
        "latestRunId": run["runId"],
        "activeRunId": None,
        "providerInstanceId": "claudeAgent",
        "model": model,
        "modelSelection": {"instanceId": "claudeAgent", "model": model.split("/")[-1]},
        "runtimeMode": "full-access",
        "interactionMode": "default",
        "linkedPullRequest": None,
        "pullRequests": [],
        "titleRegeneration": None,
        "branch": None,
        "worktreePath": None,
        "parentThreadId": None,
        "relationshipToParent": None,
        "runCount": 1,
        "itemCount": 3,
        "archived": False,
        "settled": True,
        "settledAt": "2026-11-03T16:35:00.000Z",
        "snoozed": False,
        "snoozedUntil": None,
        "pinned": False,
        "createdAt": "2026-11-03T16:25:00.000Z",
        "updatedAt": "2026-11-03T16:35:00.000Z",
        "sessionId": "session-0002",
        "runs": [run],
        "lastError": None,
        "clientRequestId": None,
        "titleDirty": False,
        "taskType": None,
        "mode": "auto",
    }


def _write_hub(
    root: Path,
    *,
    threads: list[dict],
    log_lines: list[str],
    transcripts: dict[str, list[dict]],
) -> Path:
    hub = root / "hub"
    (hub / "transcripts").mkdir(parents=True, exist_ok=True)
    (hub / "threads.json").write_text(
        json.dumps({t["threadId"]: t for t in threads}, indent=2), encoding="utf-8"
    )
    ordered = sorted(log_lines, key=lambda line: line[:19])
    (hub / "hub.log").write_text("\n".join(ordered) + "\n", encoding="utf-8")
    for thread_id, entries in transcripts.items():
        path = hub / "transcripts" / _transcript_name(thread_id)
        with path.open("w", encoding="utf-8") as fh:
            for entry in entries:
                fh.write(json.dumps(entry) + "\n")
    return hub


def _build_hub(
    root: Path,
    *,
    runs: list[dict] | None = None,
    pull_requests: list[dict] | None = None,
    merge_at: str | None = "2026-11-03T16:15:00Z",
    task_model: str = TASK_MODEL,
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
    extra_log: tuple[str, ...] = (),
) -> Path:
    """Write a synthetic hub tree (threads.json + hub.log + transcripts)."""
    if runs is None:
        runs = [_run(TASK_RUN_1)]
    if pull_requests is None:
        pull_requests = [_pull_request()]
    task_thread = {
        "threadId": TASK_THREAD_ID,
        "projectId": PROJECT_ID,
        "title": task_title,
        "createdBy": "agent",
        "creationSource": "mcp",
        "status": runs[-1].get("status", "completed"),
        "latestRunId": runs[-1]["runId"],
        "activeRunId": None,
        "providerInstanceId": "codex",
        "model": task_model,
        "modelSelection": {"instanceId": "codex", "model": task_model.split("/")[-1]},
        "runtimeMode": "full-access",
        "interactionMode": "default",
        "linkedPullRequest": pull_requests[0] if pull_requests else None,
        "pullRequests": pull_requests,
        "titleRegeneration": None,
        "branch": "empryo/mo-124-session-traces",
        "worktreePath": WORKTREE,
        "parentThreadId": None,
        "relationshipToParent": None,
        "runCount": len(runs),
        "itemCount": 6,
        "archived": True,
        "settled": True,
        "settledAt": runs[-1]["completedAt"],
        "snoozed": False,
        "snoozedUntil": None,
        "pinned": False,
        "createdAt": runs[0]["startedAt"],
        "updatedAt": runs[-1]["completedAt"],
        "sessionId": "session-0001",
        "runs": runs,
        "lastError": None,
        "clientRequestId": None,
        "titleDirty": False,
        "taskType": None,
        "mode": "auto",
    }
    threads = [task_thread]
    transcripts = {TASK_THREAD_ID: _task_transcript(runs)}
    log_lines = [
        f"{_hub_stamp('2026-11-03T16:00:00Z')} engine started for {WORKTREE} pid 4242",
        f"{_hub_stamp('2026-11-03T16:00:02Z')} {TASK_THREAD_ID} routed to {task_model} "
        "instead of anthropic/claude-opus-5-5 (circuit for anthropic is open)",
        f"{_hub_stamp(runs[0]['completedAt'])} {TASK_THREAD_ID} run {runs[0]['runId']} "
        f"completed on {task_model} (end_turn)",
    ]
    if merge_at:
        log_lines.append(
            f"{_hub_stamp(merge_at)} merged shyamsivakumar/mac-ops#99 (merge) "
            f"for {TASK_THREAD_ID}"
        )
    if review:
        review_run = _run(
            REVIEW_RUN_1,
            started_at=review_run_times[0],
            completed_at=review_run_times[1],
            cost_usd=0.1,
            steps=2,
        )
        threads.append(
            _review_thread(
                title=review_title,
                model=review_model,
                project_id=review_project_id,
                run=review_run,
            )
        )
        transcripts[REVIEW_THREAD_ID] = _review_transcript(
            review_verdict,
            started_at=review_run_times[0],
            completed_at=review_run_times[1],
        )
        log_lines.append(
            f"{_hub_stamp(review_run_times[1])} {REVIEW_THREAD_ID} run {REVIEW_RUN_1} "
            f"completed on {review_model} (end_turn)"
        )
    log_lines.extend(extra_log)
    return _write_hub(
        root, threads=threads, log_lines=log_lines, transcripts=transcripts
    )


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
        # Merge before run end so the merge can be credited when appropriate.
        self.hub = _build_hub(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _collect(self, hub: Path | None = None):
        return collect_runs(
            since=WINDOW_SINCE,
            until=WINDOW_UNTIL,
            hub_path=hub or self.hub,
        )

    def _task_trace(self, traces: list[dict]) -> dict:
        matches = [t for t in traces if t.get("thread_id") == TASK_THREAD_ID]
        self.assertEqual(len(matches), 1, "expected exactly one task-thread trace")
        return matches[0]

    def test_collect_builds_trace_without_command_secrets(self):
        traces = self._collect()
        task = self._task_trace(traces)
        self.assertEqual(task["task_key"], "MO-124")
        self.assertEqual(task["tool_call_count"], 3)
        names = [call["name"] for call in task["tool_calls"]]
        self.assertIn("command_execution", names)
        self.assertTrue(all("synthetic-password" not in name for name in names))
        self.assertEqual(task["status"], "completed")
        self.assertIn("gpt-6.1-terra", str(task.get("model")))
        blob = json.dumps(task)
        self.assertNotIn("sk-secret", blob)
        self.assertNotIn("synthetic-password", blob)
        for sentinel in ALL_SENTINELS:
            self.assertNotIn(sentinel, blob)
        # Tool entries never carry the command text or the tool title.
        for call in task["tool_calls"]:
            self.assertNotIn(COMMAND_SENTINEL, json.dumps(call))
            self.assertNotIn(TOOL_TITLE_SENTINEL, json.dumps(call))
        self.assertEqual(task["pull_requests"][0]["number"], 99)
        # The hub log recorded the routing fallback for this thread.
        self.assertTrue(task.get("model_fallback"))
        self.assertEqual(task.get("fallback_model"), TASK_MODEL)
        self.assertEqual(task.get("base_model"), "anthropic/claude-opus-5-5")

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
        # hub.log records the merge before the run ended → merge is credited.
        self.assertTrue(scored["merged_pr"])
        # The hub has no CI snapshot: never claim proof we cannot see.
        self.assertEqual(scored["proof_status"], "missing")
        self.assertFalse(scored["claimed_done_with_proof"])
        self.assertNotIn("claimed_done_without_proof", scored["flags"])
        summary = evaluate_day("2026-11-03", root=self.root)
        self.assertEqual(summary["merged_pr_count"], 1)
        self.assertEqual(summary["claimed_done_with_proof"], 0)

    def test_later_snapshot_ci_does_not_disprove(self):
        prs, _ = _pr_outcomes_for_run(
            {"pullRequests": [{"repository": "o/r", "number": 1, "snapshot": {
                "state": "merged", "mergedAt": "2026-11-03T16:15:00Z",
                "syncedAt": "2026-11-03T18:00:00Z", "checksState": "failing",
                "reviewDecision": "CHANGES_REQUESTED"}}]},
            completed_at="2026-11-03T16:20:00Z", status="completed",
        )
        self.assertIsNone(prs[0]["checks_state"])
        self.assertIsNone(prs[0]["review_decision"])
        pr = _pull_request()
        pr["snapshot"] = {"state": "merged", "mergedAt": "2026-11-03T16:15:00Z", "syncedAt": "2026-11-03T18:00:00Z", "checksState": "failing", "reviewDecision": "CHANGES_REQUESTED"}
        hub = _build_hub(self.root / "late", pull_requests=[pr])
        trace = self._task_trace(self._collect(hub))
        self.assertIsNone(trace["pull_requests"][0]["checks_state"])
        scored = score_trace(trace)
        self.assertTrue(scored["merged_pr"])
        self.assertEqual(scored["proof_status"], "missing")
        self.assertNotIn("claimed_done_without_proof", scored["flags"])

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

    def test_post_run_merge_and_interrupted_not_proven(self):
        hub = _build_hub(
            self.root / "interrupted",
            runs=[
                _run(
                    TASK_RUN_1,
                    status="interrupted",
                    stop_reason="cancelled",
                )
            ],
            merge_at="2026-11-03T16:30:00Z",
        )
        traces = self._collect(hub)
        task = self._task_trace(traces)
        scored = score_trace(task)
        self.assertFalse(scored["merged_pr"])
        self.assertFalse(scored["claimed_done_with_proof"])
        self.assertEqual(scored["proof_status"], "n/a")
        self.assertEqual(task["pull_requests"][0]["timing"], "post_run_merge")

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
        hub = _build_hub(
            self.root / "dup",
            runs=[
                _run(TASK_RUN_1),
                _run(
                    TASK_RUN_2,
                    ordinal=2,
                    started_at="2026-11-03T16:25:00.000Z",
                    completed_at="2026-11-03T16:35:00.000Z",
                ),
            ],
        )
        traces = self._collect(hub)
        task_traces = [t for t in traces if t.get("thread_id") == TASK_THREAD_ID]
        self.assertEqual(len(task_traces), 2)
        for t in task_traces:
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
            {"pullRequests": [{"url": "https://github.com/o/r/pull/1", "repository": "o/r", "number": 1,
              "snapshot": {"state": "merged", "mergedAt": "2026-11-03T16:30:00Z", "checksState": "failing", "reviewDecision": "CHANGES_REQUESTED"}}]},
            completed_at="2026-11-03T16:20:00Z", status="interrupted",
        )
        self.assertIsNone(prs[0]["checks_state"])
        self.assertIsNone(prs[0]["review_decision"])
        scored = score_trace(
            {
                "status": "interrupted",
                "outcome_evidence": "known",
                "named_blocker": None,
                "files_outside_worktree": [],
                "preview_or_playwright": [],
                "pull_requests": prs,
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

    def _task_trace(self, hub: Path) -> dict:
        traces = collect_runs(
            since=WINDOW_SINCE,
            until=WINDOW_UNTIL,
            hub_path=hub,
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
