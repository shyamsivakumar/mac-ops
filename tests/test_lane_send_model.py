"""A lane-driver send goes only to a thread whose model may take it.

A thread on a blocked model, and a legacy thread on a model no list
names, take no message: the work starts again on the first unblocked
entry of the list the lane sends with, in the thread's own worktree when
it has one. A thread on a model that may take the send is sent to as
before.
"""

import datetime
import importlib.util
import json
import sys
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import mock_open, patch

ROOT = Path(__file__).resolve().parents[1]
LANE_DIR = ROOT / "coordinator" / "overnight"
REPO = "shyamsivakumar/mac-ops"
HEAD = "a" * 40
KEY = f"fix:{REPO}#385:{HEAD}"
WORKTREE = "/tmp/fixture-worktree"

SOL = {"providerInstanceId": "openai-api", "model": "gpt-5.6-sol"}
MINIMAX = {"providerInstanceId": "minimax", "model": "minimax/MiniMax-M3.1-Flash"}
SONNET = {"providerInstanceId": "claudeAgent", "model": "claude-sonnet-5-5"}


def load_lane():
    """The lane driver, loaded the way the other lane tests load it."""
    if str(LANE_DIR) not in sys.path:
        sys.path.insert(0, str(LANE_DIR))
    loader = SourceFileLoader("lane_driver", str(LANE_DIR / "lane_driver.py"))
    spec = importlib.util.spec_from_loader("lane_driver", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class SendModelTests(unittest.TestCase):
    def setUp(self):
        self.lane = load_lane()
        self.lists = self.lane.model_list.read_json(self.lane.model_list.SEED_PATH)
        self.commands = []

    def send(self, thread, blocked=frozenset(), root=False, list_name=None, with_pr=True,
             on_origin=True, branch="builder/topic"):
        """Send to one thread and return the queue command the lane made."""
        lane = self.lane

        def run(cmd, timeout=150):
            if cmd[0] == lane.COORDQ:
                self.commands.append(cmd)
                return "receipt"
            if "--abbrev-ref" in cmd:
                return branch + "\n"
            return "ref\trefs/heads/builder/fixture\n" if on_origin else ""

        def t3(tool, args):
            return {"thread": thread}

        pr = {"number": 385, "state": "OPEN", "headRefName": "builder/fixture", "baseRefName": "main"}
        with patch.object(lane, "CFG", {REPO: {"key": "MO", "projectId": "fixture"}}), \
             patch.object(lane, "DRY", False), \
             patch.object(lane.model_list, "entries", side_effect=lambda name: self.lists[name]), \
             patch.object(lane.model_list, "blocked_identities", return_value=set(blocked)), \
             patch.object(lane, "read_json", return_value=pr), \
             patch.object(lane, "root_workspace", return_value=root), \
             patch.object(lane, "run", run), patch.object(lane, "t3", t3):
            lane.send("thread-1", "brief", "fix", {}, KEY, repo=REPO,
                      pr_number=385 if with_pr else None,
                      list_name=list_name or "fix")
        self.assertEqual(len(self.commands), 1)
        return self.commands[0]

    def payload(self, command):
        return json.loads(command[2])

    def identity(self, thread):
        """The blocked-store identity of a thread's model."""
        return self.lane.model_list.identity(
            {"instanceId": thread["providerInstanceId"], "model": thread["model"]})

    def test_a_blocked_model_gets_a_fresh_thread_on_the_next_entry(self):
        """A thread on the blocked first fix model takes no send."""
        thread = {**SONNET, "status": "completed", "sendable": True, "worktreePath": WORKTREE}
        command = self.send(thread, {self.identity(SONNET)})
        self.assertNotIn("--tool", command)
        self.assertEqual(self.payload(command)["modelSelection"], self.lists["fix"][1]["selection"])
        self.assertEqual(self.payload(command)["workspaceStrategy"],
                         {"type": "existing_worktree", "worktreePath": WORKTREE})

    def test_a_legacy_sol_thread_never_receives_a_build_message(self):
        """A thread on a model no list names takes no send."""
        thread = {**SOL, "status": "completed", "sendable": True, "worktreePath": WORKTREE}
        command = self.send(thread)
        self.assertNotIn("--tool", command)
        self.assertNotIn("threadId", self.payload(command))
        self.assertEqual(self.payload(command)["modelSelection"], self.lists["fix"][0]["selection"])

    def test_a_live_thread_on_a_blocked_model_is_not_left_without_a_thread(self):
        """A live thread whose model may not take the send is replaced, not held."""
        thread = {**SOL, "status": "running", "sendable": True, "worktreePath": WORKTREE}
        command = self.send(thread, {self.identity(SOL)})
        self.assertNotIn("--tool", command)
        self.assertEqual(self.payload(command)["modelSelection"], self.lists["fix"][0]["selection"])
        self.assertEqual(self.payload(command)["workspaceStrategy"],
                         {"type": "worktree", "baseRef": "origin/builder/fixture", "startFromOrigin": True})

    def test_an_allowed_model_is_sent_to_as_before(self):
        """A thread on a model of the fix list takes the message itself."""
        thread = {**SONNET, "status": "completed", "sendable": True, "worktreePath": WORKTREE}
        command = self.send(thread)
        self.assertIn("--tool", command)
        self.assertEqual(self.payload(command), {"threadId": "thread-1", "message": "brief"})

    def test_a_build_list_model_takes_the_send(self):
        """A thread on a model of the build list takes the message itself."""
        thread = {**MINIMAX, "status": "completed", "sendable": True, "worktreePath": WORKTREE}
        command = self.send(thread)
        self.assertIn("--tool", command)
        self.assertEqual(self.payload(command), {"threadId": "thread-1", "message": "brief"})

    def test_a_replacement_worktree_is_not_the_shared_checkout(self):
        """A thread without a worktree of its own is replaced on the branch."""
        thread = {**SOL, "status": "completed", "sendable": True}
        command = self.send(thread, root=True)
        self.assertNotIn("--tool", command)
        self.assertEqual(self.payload(command)["workspaceStrategy"],
                         {"type": "worktree", "baseRef": "origin/builder/fixture", "startFromOrigin": True})

    def test_a_build_list_model_in_the_shared_root_takes_no_send(self):
        """A newly permitted direct send never lands in the shared checkout."""
        thread = {**MINIMAX, "status": "completed", "sendable": True}
        command = self.send(thread, root=True)
        self.assertNotIn("--tool", command)
        self.assertEqual(self.payload(command)["workspaceStrategy"],
                         {"type": "worktree", "baseRef": "origin/builder/fixture", "startFromOrigin": True})

    def test_a_build_list_model_in_a_herdr_worktree_takes_no_send(self):
        """A newly permitted direct send never lands on a herdr branch."""
        thread = {**MINIMAX, "status": "completed", "sendable": True, "worktreePath": WORKTREE}
        command = self.send(thread, branch="herdr/example")
        self.assertNotIn("--tool", command)
        self.assertEqual(self.payload(command)["workspaceStrategy"],
                         {"type": "worktree", "baseRef": "origin/builder/fixture", "startFromOrigin": True})

    def test_the_first_fix_model_in_the_shared_root_still_takes_the_send(self):
        """The send the lane made before this change is unchanged."""
        thread = {**SONNET, "status": "completed", "sendable": True}
        command = self.send(thread, root=True)
        self.assertIn("--tool", command)
        self.assertEqual(self.payload(command), {"threadId": "thread-1", "message": "brief"})

    def test_a_herdr_worktree_is_not_reused(self):
        """A replacement never starts on a herdr branch."""
        thread = {**SOL, "status": "completed", "sendable": True, "worktreePath": WORKTREE}
        command = self.send(thread, branch="herdr/example")
        self.assertNotIn("--tool", command)
        self.assertEqual(self.payload(command)["workspaceStrategy"],
                         {"type": "worktree", "baseRef": "origin/builder/fixture", "startFromOrigin": True})

    def test_a_branch_that_is_not_on_origin_keeps_the_message(self):
        """A replacement with no safe base queues nothing and is retried."""
        lane = self.lane
        thread = {**SOL, "status": "running", "sendable": True, "worktreePath": WORKTREE}
        commands = []

        def run(cmd, timeout=150):
            commands.append(cmd)
            return "ref\trefs/heads/builder/fixture\n" if cmd[0] == lane.COORDQ else ""

        with patch.object(lane, "CFG", {REPO: {"key": "MO", "projectId": "fixture"}}), \
             patch.object(lane, "DRY", False), \
             patch.object(lane.model_list, "entries", side_effect=lambda name: self.lists[name]), \
             patch.object(lane.model_list, "blocked_identities", return_value=set()), \
             patch.object(lane, "read_json", return_value={"number": 385, "state": "OPEN",
                                                           "headRefName": "builder/fixture",
                                                           "baseRefName": "main"}), \
             patch.object(lane, "root_workspace", return_value=False), \
             patch.object(lane, "run", run), \
             patch.object(lane, "t3", return_value={"thread": thread}):
            result = lane.send("thread-1", "brief", "fix", {}, KEY, repo=REPO, pr_number=385)
        self.assertTrue(result.startswith("skip"))
        self.assertEqual([c for c in commands if c[0] == lane.COORDQ], [])

    def test_a_ticket_without_a_pull_request_still_gets_a_replacement(self):
        """A thread in the shared checkout gets a replacement, not a skip."""
        thread = {**SOL, "status": "completed", "sendable": True}
        command = self.send(thread, root=True, with_pr=False)
        payload = self.payload(command)
        self.assertEqual(payload["workspaceStrategy"],
                         {"type": "worktree", "baseRef": "origin/main", "startFromOrigin": True})
        self.assertEqual(payload["modelSelection"], self.lists["fix"][0]["selection"])

    def test_a_ticket_build_is_replaced_on_the_build_list(self):
        """A build-list send starts the replacement on the build list."""
        thread = {**SOL, "status": "completed", "sendable": True, "worktreePath": WORKTREE}
        command = self.send(thread, list_name="build")
        payload = self.payload(command)
        self.assertEqual(payload["modelSelection"], self.lists["build"][0]["selection"])
        self.assertEqual(payload["taskType"], "worker")

    def test_a_fix_round_is_replaced_on_the_fix_list(self):
        """A fix-list send starts the replacement on the fix list."""
        thread = {**SOL, "status": "completed", "sendable": True, "worktreePath": WORKTREE}
        command = self.send(thread, list_name="fix")
        payload = self.payload(command)
        self.assertEqual(payload["modelSelection"], self.lists["fix"][0]["selection"])
        self.assertEqual(payload["taskType"], "fix")

    def test_a_skipped_continuation_does_not_hold_the_ticket(self):
        """A continuation that queued nothing leaves the ticket eligible."""
        lane = self.lane
        reads, commands = [], []

        def t3(tool, args):
            reads.append(args)
            return {"thread": {"status": "deleted"}}

        def run(cmd, timeout=150):
            commands.append(cmd)
            return "receipt"

        def files(path, *args, **kwargs):
            data = json.dumps({f"ticket:{REPO}#385:a1": "old"}) if path == lane.RECEIPTS else "brief"
            return mock_open(read_data=data)()

        snapshot = {"repos": {REPO: {"issues": [{"number": 385, "labels": []}], "prs": []}}}
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        ledger = {"cont:old": [now, f"skip continue:{REPO}#385:old: no verified PR branch for relaunch"]}
        with patch.object(lane, "SNAPSHOT", snapshot), \
             patch.object(lane, "CFG", {REPO: {"projectId": "fixture", "key": "MO"}}), \
             patch.object(lane, "DRY", False), patch("builtins.open", files), \
             patch.object(lane.model_list, "entries", side_effect=lambda name: self.lists[name]), \
             patch.object(lane.model_list, "blocked_identities", return_value=set()), \
             patch.object(lane, "t3", t3), patch.object(lane, "run", run):
            lane.unstick(REPO, ledger)
        self.assertTrue(reads)
        self.assertEqual(len(commands), 1)


if __name__ == "__main__":
    unittest.main()
