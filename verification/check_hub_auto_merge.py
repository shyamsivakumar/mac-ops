#!/usr/bin/env python3
"""MO-159: execute selected function definitions only, never launch/import emp-hub."""
import ast
import contextlib
import uuid
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
OLD, NEW, BASE = "a" * 40, "b" * 40, "c" * 40


def definitions(home):
    tree = ast.parse((ROOT / "empryo/bin/emp-hub").read_text())
    constants = {"DEFAULT_MODEL", "INSTANCE_ROUTES", "TASK_TYPES", "PERSONAL_OWNER", "TASK_KEY", "VERDICT_LINE", "CHECK_LINE", "LEGACY_REVIEW_TITLE",
                 "NO_CHECKS_MIN_AGE_SECONDS", "NO_CHECKS_REPORTED", "REVISION_LABELS", "ISSUED_REVISIONS",
                 "ISSUED_REVISIONS_KEPT", "MERGEABLE_STATES"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) or
             isinstance(n, ast.ClassDef) and n.name == "HubError" or
             isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in n.targets)]
    h = types.ModuleType("selected_hub_definitions")
    h.__dict__.update(globals())
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "selected_hub_definitions", "exec"), h.__dict__)
    h.HUB_DIR = str(home)
    h.TRANSCRIPTS = str(home)
    h.MERGE_RECORD = str(home / "merges.jsonl")
    h.AUTO_MERGE_CONFIG = str(home / "config.json")
    if not Path(h.AUTO_MERGE_CONFIG).exists():
        Path(h.AUTO_MERGE_CONFIG).write_text(json.dumps({"autoMerge": True}))
    h.LOCK = threading.RLock()
    h.CHANGED = threading.Condition(h.LOCK)
    h.MERGE_LOCK = threading.Lock()
    h.MERGE_REPO_LOCKS = {}
    h.AUTO_MERGE_WAKE = threading.Event()
    h.LIVE = ("running", "waiting", "queued")
    h.RUNTIME = {}
    h.THREADS = types.SimpleNamespace(data={}, save=lambda: None)
    h.runtime_of = lambda key: h.RUNTIME.setdefault(key, {})
    h.thread_cwd = lambda thread: str(home)
    h.tool_thread_organize = lambda a: None
    h.tool_thread_cleanup = lambda a: {}
    h.routing = {"autoMerge": True, "autoMergeReviewerModels": ["subscriptions/claude-opus-5-5"]}
    h.load_routing = lambda: h.routing
    return h


class AutoMergeProof(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.h = h = definitions(Path(self.tmp.name))
        self.repo = "shyamsivakumar/proof"
        self.task = self.thread("task", "MO-159 task", "standard")
        self.review = self.thread("review", "MO-159 review", "review")
        self.review["runs"] = [{"runId": "review-1", "status": "completed", "startedAt": "2026-01-02T00:00:00Z",
                                "completedAt": "2026-01-03T00:00:00Z", "model": "subscriptions/claude-opus-5-5"}]
        self.review["latestRunId"] = "review-1"
        h.append_item(self.review, {"type": "assistant_message", "text": "Checked.\nVERDICT: PASS"})
        self.detail = {"number": 1, "url": "https://github.com/shyamsivakumar/proof/pull/1", "state": "OPEN",
                       "headRefName": "proof", "headRefOid": OLD, "baseRefName": "main", "isDraft": False,
                       "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN", "reviewDecision": "",
                       "isCrossRepository": False, "commits": [{"oid": OLD, "committedDate": "2026-01-01T00:00:00Z"}]}
        self.green, self.none, self.behind, self.conflict, self.changed = True, False, False, False, False
        self.failed, self.foreign = False, False
        self.commands, self.sent = [], []
        h.sh = self.command
        h.thread_repo = lambda thread: self.repo
        h.pull_requests_of = lambda thread: (self.repo, [dict(self.detail)])
        h.merge_method = lambda repo: ("squash", {})
        def send(a):
            self.assertFalse(h.runtime_of(a["threadId"]).get("merging"), "delivery must run outside the merge lease")
            self.sent.append(a)
        h.tool_thread_send = send

    def thread(self, key, title, kind):
        thread = {"threadId": key, "title": title, "taskType": kind, "projectId": "proof", "archived": False,
                  "status": "completed", "latestRunId": None, "runs": [], "branch": "proof", "worktreePath": None,
                  "pullRequests": [], "updatedAt": "2026-01-01T00:00:00Z", "itemCount": 0}
        self.h.THREADS.data[key] = thread
        return thread

    def command(self, cmd, cwd=None, timeout=120):
        self.commands.append(cmd)
        if cmd[:3] == ["gh", "pr", "view"]:
            return 0, json.dumps(self.detail), ""
        if cmd[:3] == ["gh", "pr", "checks"]:
            if self.none:
                return 1, "[]", "no checks reported"
            return (0 if self.green else 8), json.dumps([{"name": "proof", "bucket": "fail" if self.failed else "pass" if self.green else "pending"}]), ""
        if cmd[:3] == ["gh", "pr", "merge"]:
            self.detail["state"] = "MERGED"
            return 0, "merged", ""
        if cmd[:2] == ["gh", "api"] and "update-branch" in cmd[2]:
            if self.conflict:
                return 1, "", "merge conflict"
            self.detail.update(headRefOid=NEW, mergeStateStatus="CLEAN")
            self.detail["commits"].append({"oid": NEW, "committedDate": "2026-01-04T00:00:00Z"})
            self.behind, self.green = False, False
            return 0, json.dumps({"message": "Updating pull request branch"}), ""
        if "merge-base" in cmd:
            if "--is-ancestor" in cmd:
                return (1 if self.behind or (self.foreign and cmd[-2] == "d" * 40) else 0), "", ""
            return 0, BASE, ""
        if "merge-tree" in cmd:
            return (1 if self.conflict else 0), "d" * 40, ""
        if "diff" in cmd:
            changed = self.changed and self.detail["headRefOid"] == NEW
            return 0, "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+" + ("changed" if changed else "new") + "\n", ""
        if "rev-parse" in cmd:
            return 0, BASE if cmd[-1] == "FETCH_HEAD" else self.detail["headRefOid"], ""
        if cmd[:2] == ["gh", "api"]:
            return 0, json.dumps({"sha": self.detail["headRefOid"], "parents": [{"sha": OLD}, {"sha": "d" * 40 if self.foreign else BASE}],
                                  "commit": {"committer": {"date": "2026-01-01T00:00:00Z"}}}), ""
        return 0, "", ""

    def set_enabled(self, enabled):
        Path(self.h.AUTO_MERGE_CONFIG).write_text(json.dumps({"autoMerge": enabled}))

    def enqueue(self):
        self.h.enqueue_auto_merge(self.review)

    def tick(self):
        self.h.auto_merge_tick()

    def merges(self):
        return [c for c in self.commands if c[:3] == ["gh", "pr", "merge"]]

    def records(self):
        p = Path(self.h.MERGE_RECORD)
        return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []

    def test_pass_green_once_even_after_repeat_event_and_reload(self):
        self.enqueue()
        self.tick()
        self.enqueue()
        self.tick()
        self.assertEqual(len(self.merges()), 1)
        self.assertIn("--match-head-commit", self.merges()[0])
        self.assertEqual(sum(r.get("automatic", False) and r["merged"] for r in self.records()), 1)
        self.assertTrue(any(i["type"] == "notice" for i in self.h.read_items(self.task)))

    def test_fail_stale_and_disallowed_reviewer(self):
        for mode in ("fail", "stale", "model"):
            with self.subTest(mode=mode):
                self.setUp()
                if mode == "fail":
                    self.h.append_item(self.review, {"type": "assistant_message", "text": "VERDICT: FAIL"})
                if mode == "stale":
                    self.task["runs"] = [{"completedAt": "2026-01-04T00:00:00Z"}]
                if mode == "model":
                    self.review["runs"][-1]["model"] = "untrusted/model"
                self.enqueue()
                self.tick()
                self.assertEqual(self.merges(), [])
                self.assertTrue(any(r.get("reason") for r in self.records()))

    def test_pending_then_green(self):
        self.green = False
        self.enqueue()
        self.tick()
        self.assertEqual(self.merges(), [])
        self.green = True
        self.tick()
        self.assertEqual(len(self.merges()), 1)

    def test_behind_clean_update_waits_and_carries_unchanged_patch(self):
        self.behind = True
        self.detail["mergeStateStatus"] = "BEHIND"
        self.enqueue()
        self.tick()
        self.assertEqual(self.merges(), [])
        self.assertTrue(any("update-branch" in " ".join(c) for c in self.commands))
        self.tick()
        self.assertEqual(self.merges(), [])
        self.green = True
        self.tick()
        self.assertEqual(len(self.merges()), 1)
        self.assertEqual(self.merges()[0][-1], NEW)
        self.assertTrue(any(r.get("patchIdUnchanged") for r in self.records()))

    def test_changed_patch_requests_review_and_conflict_returns_to_builder(self):
        for conflict in (False, True):
            with self.subTest(conflict=conflict):
                self.setUp()
                self.behind, self.conflict, self.changed = True, conflict, not conflict
                self.detail["mergeStateStatus"] = "BEHIND"
                self.enqueue()
                self.tick()
                self.green = True
                self.tick()
                self.assertEqual(self.merges(), [])
                self.assertTrue(self.sent)
                self.assertEqual(self.sent[0]["threadId"], "task" if conflict else "review")

    def test_ascend_and_disabled_never_merge_or_update(self):
        for disabled in (False, True):
            with self.subTest(disabled=disabled):
                self.setUp()
                if disabled:
                    self.set_enabled(False)
                else:
                    self.repo = "slash-eureka/proof"
                self.behind = True
                self.enqueue()
                self.tick()
                self.assertEqual(self.merges(), [])
                self.assertFalse(any("update-branch" in " ".join(c) for c in self.commands))
                self.assertTrue(any(r.get("reason") for r in self.records()))

    def test_serial_queue_does_not_overtake_pending_head(self):
        self.green = False
        self.enqueue()
        first = self.task
        second = self.thread("task-2", "MO-160 task", "standard")
        review = self.thread("review-2", "MO-160 review", "review")
        review["runs"] = [dict(self.review["runs"][0], runId="review-2")]
        review["latestRunId"] = "review-2"
        self.h.append_item(review, {"type": "assistant_message", "text": "VERDICT: PASS"})
        self.h.enqueue_auto_merge(review)
        self.tick()
        self.assertEqual(self.merges(), [])
        self.assertNotEqual(second["autoMerge"]["state"], "merged")
        self.green = True
        self.tick()
        self.assertEqual(first["autoMerge"]["state"], "merged")
        self.assertNotEqual(second["autoMerge"]["state"], "merged")


    def report(self, text):
        Path(self.h.transcript_path(self.review)).unlink()
        self.h.append_item(self.review, {"type": "assistant_message", "text": text})

    def test_no_checks_requires_exact_check_line_and_age(self):
        self.none = True
        self.enqueue()
        self.tick()
        self.assertEqual(self.merges(), [])
        self.report(f"CHECK: PASS {OLD}\nVERDICT: PASS")
        self.tick()
        self.assertEqual(len(self.merges()), 1)

    def test_no_check_receipt_carries_only_across_verified_update(self):
        self.none, self.behind = True, True
        self.detail["mergeStateStatus"] = "BEHIND"
        self.report(f"CHECK: PASS {OLD}\nVERDICT: PASS")
        self.enqueue()
        self.tick()
        self.tick()
        self.tick()
        self.assertEqual(len(self.merges()), 1)
        self.assertEqual(self.merges()[0][-1], NEW)
        self.assertEqual(self.task["autoMerge"]["carry"]["originalHead"], OLD)

    def test_no_checks_fresh_head_does_not_merge(self):
        self.none = True
        self.detail["commits"][0]["committedDate"] = self.h.now_iso()
        self.report(f"CHECK: PASS {OLD}\nVERDICT: PASS")
        self.enqueue()
        self.tick()
        self.assertEqual(self.merges(), [])

    def test_disabled_pause_can_resume_without_new_review(self):
        self.set_enabled(False)
        self.enqueue()
        self.tick()
        self.set_enabled(True)
        self.tick()
        self.assertEqual(len(self.merges()), 1)

    def test_task_rerun_and_new_review_fail_are_not_bypassed(self):
        self.enqueue()
        self.task["latestRunId"] = "task-new"
        self.tick()
        self.assertEqual(self.merges(), [])
        self.assertIn("run changed", self.task["autoMerge"]["reason"])
        self.task["latestRunId"] = None
        self.review["latestRunId"] = "review-2"
        self.review["runs"][-1]["runId"] = "review-2"
        self.report("VERDICT: FAIL")
        self.enqueue()
        self.tick()
        self.assertEqual(self.merges(), [])

    def test_draft_fork_closed_and_ascend_key_do_not_update(self):
        for field, value in (("isDraft", True), ("isCrossRepository", True), ("state", "CLOSED"), ("key", "OPS")):
            with self.subTest(field=field):
                self.setUp()
                if field == "key":
                    self.task["title"] = "OPS-1 task"
                    self.review["title"] = "OPS-1 review"
                else:
                    self.detail[field] = value
                self.behind = True
                self.enqueue()
                self.tick()
                self.assertEqual(self.merges(), [])
                self.assertFalse(any("update-branch" in " ".join(c) for c in self.commands))

    def test_checks_or_head_change_between_dry_run_and_merge(self):
        for head_change in (False, True):
            with self.subTest(head_change=head_change):
                self.setUp()
                original = self.h.sh
                calls = []
                def command(cmd, **kwargs):
                    result = original(cmd, **kwargs)
                    if cmd[:3] == ["gh", "pr", "checks"]:
                        calls.append(cmd)
                        if head_change:
                            self.detail["headRefOid"] = NEW
                        elif len(calls) == 1:
                            self.green = False
                    return result
                self.h.sh = command
                self.enqueue()
                self.tick()
                self.assertEqual(self.merges(), [])

    def test_restart_recovers_waiting_update_and_post_merge_crash(self):
        self.behind = True
        self.detail["mergeStateStatus"] = "BEHIND"
        self.enqueue()
        self.tick()
        stored = json.loads(json.dumps(self.h.THREADS.data))
        home = Path(self.tmp.name)
        self.h = h = definitions(home)
        h.THREADS.data = stored
        self.task, self.review = stored["task"], stored["review"]
        h.sh = self.command
        h.thread_repo = lambda thread: self.repo
        h.pull_requests_of = lambda thread: (self.repo, [dict(self.detail)])
        h.merge_method = lambda repo: ("squash", {})
        self.tick()
        self.green = True
        self.tick()
        self.assertEqual(len(self.merges()), 1)
        self.task["autoMerge"]["state"] = "waiting"  # Crash before success state was saved.
        self.tick()
        self.assertEqual(len(self.merges()), 1)
        self.assertEqual(self.task["autoMerge"]["state"], "skipped")

    def test_repo_lock_and_run_lease_serialize_manual_and_auto(self):
        self.enqueue()
        entered, finished = threading.Event(), threading.Event()
        def contender():
            entered.set()
            self.h.tool_thread_merge({"threadId": "task", "dryRun": True})
            finished.set()
        with self.h.merge_repo_lock(self.repo), self.h.merge_guard(self.task, self.task["autoMerge"]):
            worker = threading.Thread(target=contender)
            worker.start()
            self.assertTrue(entered.wait(2))
            self.assertFalse(finished.is_set())
            self.assertTrue(self.h.runtime_of("task")["merging"])
        worker.join(2)
        self.assertTrue(finished.is_set())
        self.assertIsNone(self.h.runtime_of("task")["merging"])

    def test_real_git_clean_update_patch_id_and_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            def git(*args):
                return subprocess.run(["git", *args], cwd=tmp, capture_output=True, text=True, check=True).stdout.strip()
            git("init", "-b", "main")
            git("config", "user.name", "Proof")
            git("config", "user.email", "proof@example.invalid")
            path = Path(tmp) / "own"
            path.write_text("old\n")
            git("add", ".")
            git("commit", "-m", "base")
            git("checkout", "-b", "pr")
            path.write_text("new\n")
            git("commit", "-am", "own diff")
            head = git("rev-parse", "HEAD")
            git("checkout", "main")
            (Path(tmp) / "main-only").write_text("base change\n")
            git("add", ".")
            git("commit", "-m", "advance main")
            base = git("rev-parse", "HEAD")
            self.h.sh = lambda cmd, cwd=None, timeout=120: self._real_command(cmd, tmp, timeout)
            before = self.h.train_patch_id(self.task, base, head)
            tree = git("merge-tree", "--write-tree", base, head)
            git("checkout", "pr")
            git("merge", "main", "--no-edit")
            updated = git("rev-parse", "HEAD")
            self.assertEqual(before, self.h.train_patch_id(self.task, base, updated))
            self.assertEqual(tree, git("rev-parse", "HEAD^{tree}"))
            git("checkout", "main")
            path.write_text("conflicting\n")
            git("commit", "-am", "conflict")
            result = subprocess.run(["git", "merge-tree", "--write-tree", "main", head], cwd=tmp, capture_output=True)
            self.assertEqual(result.returncode, 1)

    def test_foreign_merge_parent_never_carries_review(self):
        self.behind = True
        self.detail["mergeStateStatus"] = "BEHIND"
        self.enqueue()
        self.tick()
        self.foreign = True
        self.tick()
        self.green = True
        self.tick()
        self.assertEqual(self.merges(), [])
        self.assertNotIn("carry", self.task["autoMerge"])
        self.assertEqual(self.sent[0]["threadId"], "review")

    def test_red_checks_and_requested_changes_release_head_without_update(self):
        for changes_requested in (False, True):
            with self.subTest(changes_requested=changes_requested):
                self.setUp()
                self.behind, self.failed = True, not changes_requested
                self.detail["mergeStateStatus"] = "BEHIND"
                self.detail["reviewDecision"] = "CHANGES_REQUESTED" if changes_requested else ""
                self.enqueue()
                self.tick()
                self.assertEqual(self.merges(), [])
                self.assertFalse(any("update-branch" in " ".join(c) for c in self.commands))
                self.assertEqual(self.task["autoMerge"]["state"], "blocked")
                self.assertEqual(self.sent[0]["threadId"], "task")

    def test_pending_update_and_waiting_head_have_bounded_wait(self):
        for update in (False, True):
            with self.subTest(update=update):
                self.setUp()
                self.behind, self.green = update, update
                if update:
                    self.detail["mergeStateStatus"] = "BEHIND"
                self.enqueue()
                self.tick()
                if update:
                    self.detail["headRefOid"] = OLD
                    self.task["autoMerge"]["update"]["requestedAt"] = "2026-01-01T00:00:00Z"
                else:
                    self.task["autoMerge"]["waitSince"] = "2026-01-01T00:00:00Z"
                self.tick()
                self.assertEqual(self.merges(), [])
                self.assertEqual(self.task["autoMerge"]["state"], "blocked")
                self.assertEqual(self.sent[0]["threadId"], "task")

    def test_update_requires_github_behind_state(self):
        self.behind = True
        self.enqueue()
        self.tick()
        self.assertFalse(any("update-branch" in " ".join(c) for c in self.commands))
        self.detail["mergeStateStatus"] = "BEHIND"
        self.tick()
        self.assertTrue(any("update-branch" in " ".join(c) for c in self.commands))
        self.assertEqual(self.merges(), [])

    def test_polling_does_not_duplicate_audit_events(self):
        self.green = False
        self.enqueue()
        self.tick()
        count = len(self.records())
        self.tick()
        self.tick()
        self.assertEqual(len(self.records()), count)

    def test_config_missing_or_bad_is_disabled_and_installs_cannot_enable(self):
        config = Path(self.h.AUTO_MERGE_CONFIG)
        for text in ("{}", "null", "{bad", '{"autoMerge": false}'):
            config.write_text(text)
            self.h.routing["autoMerge"] = True  # An installer replaces routing, not this state file.
            self.assertFalse(self.h.auto_merge_enabled())
        config.unlink()
        self.assertFalse(self.h.auto_merge_enabled())
        self.set_enabled(True)
        self.assertTrue(self.h.auto_merge_enabled())

    def test_existing_merge_evidence_assertions_without_importing_hub(self):
        source = ast.parse((ROOT / "verification/check_hub_merge_evidence.py").read_text())
        nodes = [n for n in source.body if isinstance(n, ast.ClassDef)]
        namespace = dict(globals(), REPORT="Checked every change and the builder proof.\nVERDICT: PASS",
                         HEAD_SHA=OLD, FALLBACK_MODEL="subscriptions/gpt-6.1-terra", REVIEW_RUN_ID="run-review-1")
        def legacy_loader(home):
            h = definitions(home)
            h.PROJECTS = types.SimpleNamespace(data={}, save=lambda: None)
            h.WORKTREES, h.ROUTING_PATH = str(home / "worktrees"), str(home / "routing.json")
            h.routing = json.loads((ROOT / "empryo/hub/routing.json").read_text())
            h.caller_thread = lambda: None
            h.dispatch = lambda request: h.tool_thread_merge(request["arguments"])
            return h
        namespace.update(load_hub=legacy_loader, io=__import__("io"), contextlib=contextlib)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "existing_merge_evidence_assertions", "exec"), namespace)
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(namespace["MergeEvidenceProof"])
        result = unittest.TestResult()
        suite.run(result)
        self.assertEqual(result.testsRun, 7)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.failures, [])

    @staticmethod
    def _real_command(cmd, cwd, timeout):
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout.strip(), result.stderr.strip()


if __name__ == "__main__":
    unittest.main()
