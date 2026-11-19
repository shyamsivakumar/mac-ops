"""The lane never sends work to a repository root or to a herdr branch.

A send to a thread that works in the shared root of a repository is
refused: the work starts a fresh thread in a worktree of the pull
request's branch instead, so the branch everyone installs from never
moves. A thread whose worktree is on a branch under `herdr/` is refused
the same way, and a pull request on a herdr branch takes no work at all.
"""

import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
LANE_DIR = ROOT / "coordinator" / "overnight"
REPO = "shyamsivakumar/mac-ops"
ROOT_CHECKOUT = "/Users/shyamsivakumar/Code/mac-ops"
WORKTREE = "/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-fixture"
KEY = f"fix:{REPO}#512:head"
SELECTION = {"instanceId": "fixture", "model": "fixture-model"}
# The root checkout keeps the common git directory of the repository; a
# linked worktree keeps its own.
ROOT_GIT = ".git\n.git\n"
WORKTREE_GIT = f"{ROOT_CHECKOUT}/.git/worktrees/t3-fixture\n{ROOT_CHECKOUT}/.git\n"


def load_lane():
    if str(LANE_DIR) not in sys.path:
        sys.path.insert(0, str(LANE_DIR))
    if "lane_driver" in sys.modules:
        return sys.modules["lane_driver"]
    loader = SourceFileLoader("lane_driver", str(LANE_DIR / "lane_driver.py"))
    spec = importlib.util.spec_from_loader("lane_driver", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    sys.modules["lane_driver"] = module
    return module


class WorkspaceGuardTests(unittest.TestCase):
    def setUp(self):
        self.lane = load_lane()

    def send_to(self, thread, pr=None, git=WORKTREE_GIT, branch="refs/heads/builder/fixture"):
        """Send to one thread and report what the lane did with it."""
        actions, launches = [], []

        def read(tool, args):
            return {"thread": {"providerInstanceId": SELECTION["instanceId"],
                               "model": SELECTION["model"], "status": "running", **thread}}

        def command(cmd, timeout=150):
            if cmd[0] == "git":
                if "rev-parse" in cmd:
                    return git
                if "symbolic-ref" in cmd:
                    return branch
                raise AssertionError(f"unexpected git command: {cmd}")
            payload = json.loads(cmd[2])
            actions.append("send" if payload.get("threadId") else "fresh")
            if not payload.get("threadId"):
                launches.append(payload)
            return "receipt"

        pull = pr or dict(number=512, state="OPEN", headRefName="builder/fixture", baseRefName="main")
        output = io.StringIO()
        with patch.object(self.lane, "CFG", {REPO: {"projectId": "fixture", "key": "MO"}}), \
             patch.object(self.lane, "DRY", False), patch.object(self.lane, "t3", read), \
             patch.object(self.lane, "read_json", return_value=pull), \
             patch.object(self.lane, "branch_on_origin", return_value=True), \
             patch.object(self.lane.model_list, "first_available",
                          return_value={"id": "fixture", "selection": SELECTION}), \
             patch.object(self.lane.model_list, "same_selection", return_value=True), \
             patch.object(self.lane, "run", command), redirect_stdout(output):
            result = self.lane.send("old", "brief", "MO#512 fix", {}, KEY, repo=REPO, pr_number=512)
        return result, actions, launches, output.getvalue()

    def test_a_send_to_a_root_workspace_thread_is_refused(self):
        """The shared root of a repository takes no work."""
        result, actions, launches, output = self.send_to({"worktreePath": ROOT_CHECKOUT}, git=ROOT_GIT)
        self.assertEqual(actions, ["fresh"])
        self.assertEqual(result, "fresh (old root workspace): receipt")
        self.assertEqual(launches[0]["workspaceStrategy"],
                         {"type": "worktree", "baseRef": "origin/builder/fixture", "startFromOrigin": True})
        self.assertEqual(output.splitlines(), ["SEND REFUSED old: root workspace"])

    def test_a_herdr_branch_takes_no_work(self):
        """A branch under `herdr/` is Shyam's, so no work goes there."""
        result, actions, launches, output = self.send_to(
            {"worktreePath": WORKTREE}, branch="refs/heads/herdr/gh-trim")
        self.assertEqual(actions, ["fresh"])
        self.assertEqual(result, "fresh (old herdr branch herdr/gh-trim): receipt")
        self.assertEqual(launches[0]["workspaceStrategy"],
                         {"type": "worktree", "baseRef": "origin/builder/fixture", "startFromOrigin": True})
        self.assertEqual(output.splitlines(), ["SEND REFUSED old: herdr branch herdr/gh-trim"])

    def test_a_pull_request_on_a_herdr_branch_takes_no_work(self):
        """The relaunch never starts on a herdr branch."""
        result, actions, launches, output = self.send_to(
            {"worktreePath": WORKTREE},
            pr=dict(number=512, state="OPEN", headRefName="herdr/gh-trim", baseRefName="main"))
        self.assertEqual((actions, launches, output), ([], [], ""))
        self.assertEqual(result, "skip #512: herdr branch, Shyam merges")

    def test_a_worktree_of_its_own_takes_the_work(self):
        """A thread that works in a worktree of its own keeps the work."""
        result, actions, launches, output = self.send_to({"worktreePath": WORKTREE})
        self.assertEqual((actions, launches, output), (["send"], [], ""))
        self.assertEqual(result, "receipt")


if __name__ == "__main__":
    unittest.main()
