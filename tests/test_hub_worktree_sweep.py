"""Tests for the hub-owned worktree sweeper in empryo/bin/emp-hub.

The module is loaded with HOME pointed at a scratch directory so its Stores
never read or write the real ~/.empryo-hub state. Git fixtures are real
temporary repositories; gh calls are replaced with in-memory pull requests.
"""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = datetime.now(timezone.utc) - timedelta(hours=25)


def run(*argv):
    result = subprocess.run([str(a) for a in argv], capture_output=True, text=True)
    assert result.returncode == 0, f"{argv} failed: {result.stderr}"
    return result.stdout.strip()


def load_hub(home):
    path = ROOT / "empryo" / "bin" / "emp-hub"
    name = f"emp_hub_test_{uuid.uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(name, path, loader=importlib.machinery.SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    previous = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = previous
    return module


class HubSweepTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.home = self.scratch.name
        self.hub = load_hub(self.home)
        self.logs = []
        self.hub.log = self.logs.append
        self.prs = {}
        self.hub.pull_requests_of = self._pull_requests_of
        base = f"{self.home}/fixture"
        os.makedirs(base)
        self.origin = f"{base}/origin.git"
        run("git", "init", "--bare", "-b", "main", self.origin)
        self.root = f"{base}/root"
        run("git", "clone", self.origin, self.root)
        run("git", "-C", self.root, "config", "user.email", "t@t")
        run("git", "-C", self.root, "config", "user.name", "t")
        with open(f"{self.root}/.gitignore", "w") as f:
            f.write(".empryo/\nnode_modules/\n")
        with open(f"{self.root}/readme.md", "w") as f:
            f.write("base\n")
        run("git", "-C", self.root, "add", "-A")
        run("git", "-C", self.root, "commit", "-m", "base")
        run("git", "-C", self.root, "push", "origin", "main")
        run("git", "-C", self.root, "remote", "set-head", "origin", "main")

    def tearDown(self):
        self.scratch.cleanup()

    def _pull_requests_of(self, thread):
        if thread["threadId"] in self.prs and self.prs[thread["threadId"]] is None:
            raise self.hub.HubError("gh pr list failed (simulated outage)")
        return "shyamsivakumar/mac-ops", self.prs.get(thread["threadId"], [])

    def add_thread(self, worktree, branch=None, task_type="standard", updated=None, status="completed", **over):
        thread = {
            "threadId": f"emp:{uuid.uuid4()}", "projectId": "proj:x", "title": f"MO-1 {task_type}",
            "status": status, "worktreePath": worktree, "branch": branch, "pullRequests": [], "archived": False,
            "settled": True, "settledAt": None, "snoozed": False, "snoozedUntil": None, "pinned": False,
            "pendingTurn": None, "sessionId": None, "runs": [], "createdAt": OLD.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "updatedAt": (updated or OLD).strftime("%Y-%m-%dT%H:%M:%S.000Z"), "taskType": task_type,
            "modelSelection": {"instanceId": "empryo", "model": "m"}, "lastError": None, "itemCount": 0, "runCount": 0,
        }
        thread.update(over)
        self.hub.THREADS.data[thread["threadId"]] = thread
        return thread

    def feature_worktree(self, name="feature"):
        run("git", "-C", self.root, "config", "user.email", "t@t")
        run("git", "-C", self.root, "checkout", "-b", name)
        with open(f"{self.root}/change.txt", "w") as f:
            f.write(f"{name}\n")
        run("git", "-C", self.root, "add", "-A")
        run("git", "-C", self.root, "commit", "-m", name)
        run("git", "-C", self.root, "push", "origin", name)
        head = run("git", "-C", self.root, "rev-parse", "HEAD")
        run("git", "-C", self.root, "checkout", "main")
        worktree = f"{self.home}/fixture/{name}-wt"
        run("git", "-C", self.root, "worktree", "add", worktree, name)
        return worktree, name, head

    def merged_pr(self, head, number=7):
        return {"number": number, "state": "MERGED", "headRefOid": head, "headRefName": "feature",
                "baseRefName": "main", "url": "https://github.com/shyamsivakumar/mac-ops/pull/7",
                "isDraft": False, "mergedAt": "2026-11-04T00:00:00Z", "isCrossRepository": False}

    def test_ignored_unsaved_file_holds_the_worktree(self):
        worktree, branch, head = self.feature_worktree()
        with open(f"{worktree}/.gitignore", "a") as f:
            f.write("secret.txt\n")
        run("git", "-C", worktree, "add", ".gitignore")
        run("git", "-C", worktree, "commit", "-m", "ignore")
        run("git", "-C", worktree, "push", "origin", f"{branch}:{branch}")
        head = run("git", "-C", worktree, "rev-parse", "HEAD")
        os.makedirs(f"{worktree}/node_modules/x")
        os.makedirs(f"{worktree}/.empryo/jobs")
        Path(f"{worktree}/.empryo/jobs/job-1.log").write_text("log")
        Path(f"{worktree}/secret.txt").write_text("unsaved")
        thread = self.add_thread(worktree, branch)
        self.prs[thread["threadId"]] = [self.merged_pr(head)]
        dirty, held = self.hub.worktree_unsaved(worktree)
        self.assertEqual(dirty, [])
        self.assertEqual(held, ["secret.txt"])
        self.hub.sweep_tick()
        self.assertTrue(os.path.isdir(worktree))
        self.assertNotIn("worktreeRemoved", thread)
        self.assertTrue(os.path.exists(f"{worktree}/secret.txt"))

    def test_worktree_unsaved_flags_untracked_and_rebuildable(self):
        worktree, _, _ = self.feature_worktree()
        os.makedirs(f"{worktree}/node_modules/pkg")
        os.makedirs(f"{worktree}/nested/node_modules/pkg")
        os.makedirs(f"{worktree}/.empryo/jobs")
        Path(f"{worktree}/.empryo/jobs/job-2.log").write_text("log")
        Path(f"{worktree}/untracked.txt").write_text("new")
        dirty, held = self.hub.worktree_unsaved(worktree)
        self.assertEqual(held, [])
        self.assertEqual(dirty, ["untracked.txt"])

    def test_merged_pr_is_removed_jobs_copied_and_logged(self):
        worktree, branch, head = self.feature_worktree()
        os.makedirs(f"{worktree}/node_modules/pkg")
        os.makedirs(f"{worktree}/.empryo/jobs")
        Path(f"{worktree}/.empryo/jobs/job-3.log").write_text("job evidence")
        thread = self.add_thread(worktree, branch)
        self.prs[thread["threadId"]] = [self.merged_pr(head)]
        self.hub.sweep_tick()
        self.assertFalse(os.path.exists(worktree))
        self.assertEqual(os.path.realpath(thread["worktreeRemoved"]["repoRoot"]), os.path.realpath(self.root))
        self.assertEqual(thread["worktreeRemoved"]["base"], "main")
        evidence_dir = thread["worktreeRemoved"]["evidenceDir"]
        self.assertTrue(os.path.exists(f"{evidence_dir}/jobs/job-3.log"))
        with open(f"{evidence_dir}/removal.json") as f:
            record = json.load(f)
        self.assertEqual(record["threadId"], thread["threadId"])
        self.assertEqual(record["evidence"]["finishedPullRequests"], [{"number": 7, "state": "MERGED"}])
        branches = run("git", "-C", self.root, "branch", "--format", "%(refname:short)")
        self.assertNotIn(branch, branches.splitlines())
        self.assertTrue(any("worktree sweep removed" in line for line in self.logs))

    def test_open_pr_or_unmerged_head_is_kept(self):
        worktree, branch, head = self.feature_worktree()
        thread = self.add_thread(worktree, branch)
        self.prs[thread["threadId"]] = [{"number": 8, "state": "OPEN", "headRefOid": head, "headRefName": branch,
                                         "baseRefName": "main", "url": "u", "isDraft": False, "mergedAt": None,
                                         "isCrossRepository": False}]
        self.hub.sweep_tick()
        self.assertTrue(os.path.isdir(worktree))

    def test_no_finished_pr_is_kept_even_with_zero_commits_ahead(self):
        worktree, branch, head = self.feature_worktree()
        run("git", "-C", self.root, "push", "origin", f"{branch}:main")  # head now on origin/main
        thread = self.add_thread(worktree, branch)
        self.prs[thread["threadId"]] = []
        self.hub.sweep_tick()
        self.assertTrue(os.path.isdir(worktree))

    def test_partial_github_failure_holds_all_removals(self):
        worktree_a, branch_a, head_a = self.feature_worktree("feature-a")
        worktree_b, branch_b, head_b = self.feature_worktree("feature-b")
        thread_a = self.add_thread(worktree_a, branch_a)
        thread_b = self.add_thread(worktree_b, branch_b)
        self.prs[thread_a["threadId"]] = [self.merged_pr(head_a)]
        self.prs[thread_b["threadId"]] = None  # simulated gh outage for one candidate
        self.hub.sweep_tick()
        self.assertTrue(os.path.isdir(worktree_a))
        self.assertTrue(os.path.isdir(worktree_b))
        self.assertTrue(any("held all" in line for line in self.logs))

    def test_restarting_thread_blocks_removal_under_the_lock(self):
        worktree, branch, head = self.feature_worktree()
        thread = self.add_thread(worktree, branch)
        self.prs[thread["threadId"]] = [self.merged_pr(head)]
        verdict, reason, evidence = self.hub.task_sweep_verdict(thread)
        self.assertEqual(verdict, "remove")
        thread["status"] = "running"
        outcome = self.hub.remove_worktree_safely(thread, evidence, "test")
        self.assertEqual(outcome["action"], "kept")
        self.assertTrue(os.path.isdir(worktree))
        thread["status"] = "completed"
        thread["pendingTurn"] = {"message": "again"}
        self.assertEqual(self.hub.remove_worktree_safely(thread, evidence, "test")["action"], "kept")
        self.assertTrue(os.path.isdir(worktree))

    def test_worktree_changed_before_removal_is_kept(self):
        worktree, branch, head = self.feature_worktree()
        thread = self.add_thread(worktree, branch)
        self.prs[thread["threadId"]] = [self.merged_pr(head)]
        verdict, _, evidence = self.hub.task_sweep_verdict(thread)
        self.assertEqual(verdict, "remove")
        Path(f"{worktree}/late.txt").write_text("appeared after the verdict")
        self.assertEqual(self.hub.remove_worktree_safely(thread, evidence, "test")["action"], "kept")
        self.assertTrue(os.path.exists(f"{worktree}/late.txt"))

    def test_review_detached_old_and_idle_is_removed(self):
        worktree, branch, head = self.feature_worktree()
        detached = f"{self.home}/fixture/review-wt"
        run("git", "-C", self.root, "worktree", "add", "--detach", detached, head)
        review = self.add_thread(detached, branch=None, task_type="review")
        self.hub.sweep_tick()
        self.assertFalse(os.path.exists(detached))
        self.assertEqual(review["worktreeRemoved"]["by"], "worktree sweep")
        self.assertIsNone(review["worktreeRemoved"]["branch"])

    def test_review_recent_shared_or_not_remote_is_kept(self):
        worktree, branch, head = self.feature_worktree()
        recent = f"{self.home}/fixture/recent-wt"
        run("git", "-C", self.root, "worktree", "add", "--detach", recent, head)
        self.add_thread(recent, branch=None, task_type="review", updated=datetime.now(timezone.utc) - timedelta(hours=1))
        shared = f"{self.home}/fixture/shared-wt"
        run("git", "-C", self.root, "worktree", "add", "--detach", shared, head)
        review = self.add_thread(shared, branch=None, task_type="review")
        self.add_thread(shared, branch=branch)  # the task thread still uses it
        run("git", "-C", self.root, "checkout", "-b", "local-only")
        Path(f"{self.root}/local.txt").write_text("never pushed\n")
        run("git", "-C", self.root, "add", "-A")
        run("git", "-C", self.root, "commit", "-m", "local")
        local_head = run("git", "-C", self.root, "rev-parse", "HEAD")
        unremote = f"{self.home}/fixture/unremote-wt"
        run("git", "-C", self.root, "worktree", "add", "--detach", unremote, local_head)
        self.add_thread(unremote, branch=None, task_type="review")
        self.hub.sweep_tick()
        self.assertTrue(os.path.isdir(recent))
        self.assertTrue(os.path.isdir(shared))
        self.assertTrue(os.path.isdir(unremote))
        self.assertNotIn("worktreeRemoved", review)

    def test_archived_live_thread_is_never_swept(self):
        worktree, branch, head = self.feature_worktree()
        thread = self.add_thread(worktree, branch, status="running", archived=True)
        self.prs[thread["threadId"]] = [self.merged_pr(head)]
        self.hub.sweep_tick()
        self.assertTrue(os.path.isdir(worktree))

    def test_removed_worktree_is_recreated_on_resume(self):
        worktree, branch, head = self.feature_worktree()
        thread = self.add_thread(worktree, branch)
        self.prs[thread["threadId"]] = [self.merged_pr(head)]
        self.hub.sweep_tick()
        self.assertFalse(os.path.exists(worktree))
        self.hub.recreate_removed_worktree(thread)
        self.assertTrue(os.path.isdir(worktree))
        self.assertTrue(thread["branch"].startswith("empryo/resume-"))
        self.assertNotIn("worktreeRemoved", thread)
        self.assertEqual(run("git", "-C", worktree, "branch", "--show-current"), thread["branch"])
        removed = thread.pop("branch")
        thread["worktreeRemoved"] = {"removedAt": "x", "repoRoot": None, "base": "main"}
        with self.assertRaises(self.hub.HubError) as ctx:
            self.hub.recreate_removed_worktree(thread)
        self.assertIn("cannot recreate", str(ctx.exception))
        thread["worktreeRemoved"]["repoRoot"] = self.root
        run("git", "-C", self.root, "worktree", "remove", "--force", worktree)
        self.hub.recreate_removed_worktree(thread)
        self.assertTrue(os.path.isdir(worktree))


if __name__ == "__main__":
    unittest.main()
