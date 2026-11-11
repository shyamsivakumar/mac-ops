#!/usr/bin/env python3
"""Merge-gate evidence proof: one record per merge-gate evaluation.

A dry run and a real merge on disposable threads each append exactly one
record to ~/.empryo-hub/merges.jsonl, a refused merge records the gate it
read, and a record that cannot be written does not fail the merge. Only
outbound command I/O is faked (gh and git): the hub runs from this repository
with HOME pointed at a temporary directory, so no production store, socket,
engine or pull request is touched.
"""
from importlib.machinery import SourceFileLoader
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HEAD_SHA = "a" * 40
REPORT = "Checked every change and the builder proof.\nVERDICT: PASS"
FALLBACK_MODEL = "subscriptions/gpt-6.1-terra"
REVIEW_RUN_ID = "run-review-1"


def load_hub(home):
    loader = SourceFileLoader("disposable_hub", str(ROOT / "empryo/bin/emp-hub"))
    hub = types.ModuleType(loader.name)
    with patch.dict(os.environ, {"HOME": str(home)}):
        loader.exec_module(hub)
    return hub


class MergeEvidenceProof(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hm-", dir="/tmp")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        h = self.hub = load_hub(self.home)
        for directory in (h.HUB_DIR, h.TRANSCRIPTS, h.WORKTREES):
            Path(directory).mkdir(parents=True, exist_ok=True)
        Path(h.ROUTING_PATH).write_text((ROOT / "empryo/hub/routing.json").read_text())
        h.PROJECTS.data["proof"] = h.new_project("proof", "disposable", str(self.home))
        h.PROJECTS.save()
        self.task = self.make_thread("MO-154 task", "standard")
        self.review = self.make_thread("MO-154 review", "review")
        self.finish_review()
        self.stub_github()

    def make_thread(self, title, task_type):
        h = self.hub
        thread = h.new_thread({"projectId": "proof", "title": title, "taskType": task_type})
        thread["branch"] = "proof-branch"
        h.THREADS.save()
        return thread

    def finish_review(self):
        h = self.hub
        self.review["runs"].append({"runId": REVIEW_RUN_ID, "ordinal": 1, "status": "completed", "startedAt": h.now_iso(),
                                    "completedAt": h.now_iso(), "stopReason": "end_turn", "usage": None,
                                    "model": FALLBACK_MODEL, "error": None})
        self.review["runCount"] = 1
        self.review["latestRunId"] = REVIEW_RUN_ID
        h.append_item(self.review, {"type": "assistant_message", "status": "completed", "text": REPORT})
        h.THREADS.save()

    def stub_github(self):
        h = self.hub
        detail = {"number": 1, "url": "https://github.com/disposable/proof/pull/1", "state": "OPEN", "isDraft": False,
                  "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN", "reviewDecision": "", "headRefOid": HEAD_SHA,
                  "baseRefName": "main", "isCrossRepository": False, "commits": []}
        h.pull_requests_of = lambda t: ("disposable/proof", [{"number": 1, "state": "OPEN", "headRefName": "proof-branch", "isCrossRepository": False}])
        h.gh_json = lambda args: dict(detail)
        h.checks_verdict = lambda repo, number: (True, None, {"count": 1, "state": "green"})
        h.merge_method = lambda repo: ("squash", {"allowed": ["squash"]})
        h.sh = lambda cmd, cwd=None, timeout=120: (0, "", "")

    def merge(self, **arguments):
        return self.hub.dispatch({"method": "call", "tool": "emp_thread_merge",
                                  "arguments": {"threadId": self.task["threadId"], **arguments}})

    def records(self):
        path = Path(self.hub.MERGE_RECORD)
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def test_dry_run_and_merge_each_write_one_record(self):
        dry = self.merge(dryRun=True)
        self.assertTrue(dry["dryRun"])
        self.assertEqual(len(self.records()), 1, "a dry run writes exactly one record")
        record = self.records()[0]
        self.assertEqual(record["threadId"], self.task["threadId"])
        self.assertEqual(record["pullRequest"], 1)
        self.assertEqual(record["headSha"], HEAD_SHA)
        self.assertEqual(record["reviewThread"], self.review["threadId"])
        self.assertEqual(record["verdictWord"], "PASS")
        self.assertEqual(record["reviewModel"], FALLBACK_MODEL)
        self.assertEqual(record["reviewRunId"], REVIEW_RUN_ID)
        self.assertEqual(record["checksState"], "green")
        self.assertFalse(record["merged"])
        self.assertTrue(record["dryRun"])
        self.assertNotIn("Checked every change", Path(self.hub.MERGE_RECORD).read_text(), "the record must not hold message text")
        merged = self.merge()
        self.assertTrue(merged["merged"])
        records = self.records()
        self.assertEqual(len(records), 2, "a real merge writes exactly one record")
        self.assertTrue(records[1]["merged"])
        self.assertFalse(records[1]["dryRun"])
        self.assertEqual(records[1]["verdictWord"], "PASS")
        self.assertEqual(records[1]["reviewModel"], FALLBACK_MODEL)

    def test_a_refused_merge_still_records_the_gate_evidence(self):
        self.hub.sh = lambda cmd, cwd=None, timeout=120: (1, "", "boom") if cmd[:2] == ["gh", "pr"] else (0, "", "")
        result = self.merge()
        self.assertFalse(result["merged"])
        records = self.records()
        self.assertEqual(len(records), 1, "a refused merge writes exactly one record")
        self.assertFalse(records[0]["merged"])
        self.assertFalse(records[0]["dryRun"])
        self.assertEqual(records[0]["verdictWord"], "PASS")

    def test_a_failed_write_does_not_fail_the_merge(self):
        blocked = self.home / "blocked"
        blocked.mkdir()
        self.hub.MERGE_RECORD = str(blocked)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = self.merge()
        self.assertTrue(result["merged"], "a record that cannot be written must not fail the merge")
        self.assertIn("merge evidence not written", output.getvalue())
        self.assertEqual(list(blocked.iterdir()), [])

    def test_a_failed_review_gate_records_the_verdict(self):
        h = self.hub
        failing = self.make_thread("MO-154 failing review", "review")
        failing["runs"].append({"runId": "run-review-fail", "ordinal": 1, "status": "completed", "startedAt": h.now_iso(),
                                 "completedAt": h.now_iso(), "stopReason": "end_turn", "usage": None,
                                 "model": "subscriptions/claude-opus-5-5", "error": None})
        failing["runCount"] = 1
        failing["latestRunId"] = "run-review-fail"
        h.append_item(failing, {"type": "assistant_message", "status": "completed", "text": "Found a critical finding.\nVERDICT: FAIL"})
        h.THREADS.save()
        self.review["updatedAt"] = "2026-01-01T00:00:00.000Z"
        failing["updatedAt"] = "2026-06-01T00:00:00.000Z"
        result = self.merge()
        self.assertFalse(result["merged"])
        self.assertIn("review gate not passed", result["refused"])
        records = self.records()
        self.assertEqual(len(records), 1, "a refused merge writes exactly one record")
        self.assertEqual(records[0]["verdictWord"], "FAIL")
        self.assertEqual(records[0]["reviewModel"], "subscriptions/claude-opus-5-5")
        self.assertEqual(records[0]["reviewRunId"], "run-review-fail")
        self.assertFalse(records[0]["merged"])

    def test_a_stale_revision_records_the_current_gate(self):
        dry = self.merge(dryRun=True)
        self.assertTrue(dry["dryRun"])
        self.hub.checks_verdict = lambda repo, number: (True, None, {"count": 1, "state": "failing: build"})
        result = self.merge(expectedRevision=dry["revision"])
        self.assertFalse(result["merged"])
        self.assertIn("the task changed since revision", result["refused"])
        records = self.records()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[1]["checksState"], "failing: build")
        self.assertFalse(records[1]["merged"])
        self.assertFalse(records[1]["dryRun"])

    def test_a_review_thread_refusal_writes_no_record(self):
        result = self.hub.dispatch({"method": "call", "tool": "emp_thread_merge", "arguments": {"threadId": self.review["threadId"]}})
        self.assertFalse(result["merged"])
        self.assertIn("is a review thread", result["refused"])
        self.assertEqual(self.records(), [])

    def test_a_live_run_refusal_writes_no_record(self):
        self.task["status"] = "running"
        result = self.merge()
        self.assertFalse(result["merged"])
        self.assertEqual(result["refused"], "the task thread still has a live run")
        self.assertEqual(self.records(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
