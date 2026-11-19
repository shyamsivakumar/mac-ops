"""A lane send to a thread on a blocked model starts one fresh thread instead."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "coordinator" / "overnight"))
import lane_driver as lane

REPO = "shyamsivakumar/mac-ops"
WT = "/work/builder"
KEY = f"fix:{REPO}#1"
CONT = f"continue:{REPO}#9:t1"
KEYS = ("modelSelection", "taskType", "message", "workspaceStrategy")
SONNET = {"instanceId": "claudeAgent", "model": "claude-sonnet-5-5"}
TERRA = {"instanceId": "codex", "model": "gpt-6.1-terra"}
MINIMAX = {"instanceId": "minimax", "model": "minimax/MiniMax-M3.1-Flash"}
GLM = {"instanceId": "glm", "model": "zai/glm-5.3"}
OWN = {"type": "existing_worktree", "worktreePath": WT}
MAIN = {"type": "worktree", "baseRef": "origin/main", "startFromOrigin": True}
PR = {**MAIN, "baseRef": "origin/builder/pr"}
MODELS = str(ROOT / "coordinator" / "models.json")
BASE = {"sendable": True, "worktreePath": WT}
PR_OK = ({"headRefName": "builder/pr"}, None)


class BlockedModelSendTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir, self.cmds, self.git, self.root = tmp.name, [], "builder/x", False
        receipts = os.path.join(self.dir, "receipts.json")
        Path(receipts).write_text(json.dumps({f"ticket:{REPO}#9:a1": "t1"}))
        issues = {"repos": {REPO: {"issues": [{"number": 9, "labels": []}], "prs": []}}}
        env = {"COORDQ_DIR": self.dir, "COORDINATOR_MODELS": MODELS}

        def run(cmd, timeout=150):
            self.cmds.append(cmd)
            return self.git if cmd[0] == "git" else "queued"

        for patcher in (
            patch.dict(os.environ, env),
            patch.object(lane, "CFG", {REPO: {"key": "MO", "projectId": "p"}}),
            patch.object(lane, "RECEIPTS", receipts),
            patch.object(lane, "SNAPSHOT", issues),
            patch.object(lane, "root_workspace", lambda thread: self.root),
            patch.object(lane, "pr_action_skip", return_value=PR_OK),
            patch.object(lane, "run", run),
            patch.object(lane, "t3", lambda tool, args: {"thread": self.thread}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def block(self, *models):
        names = {lane.model_list.identity(m): {"reason": "limit"} for m in models}
        blocked = json.dumps({"blocked": names})
        Path(self.dir, "providers-blocked.json").write_text(blocked)

    def thread_on(self, model, status, attached=False):
        pulls = [{"repository": REPO, "number": 7}] * attached
        thread = {**BASE, **model, "providerInstanceId": model["instanceId"]}
        self.thread = {**thread, "status": status, "pullRequests": pulls}

    def send(self, **kwargs):
        ledger = {}
        out = lane.send("t1", "fix it", "t", ledger, KEY, repo=REPO, **kwargs)
        return out, ledger

    def launches(self, key=KEY):
        starts = [json.loads(c[2]) for c in self.cmds if c[0] == lane.COORDQ]
        return [a for a in starts if a.get("clientRequestId") == key]

    def test_blocked_thread_is_replaced_on_the_next_entry(self):
        cases = [
            ("idle", SONNET, "completed", {}, OWN, TERRA),
            ("running", SONNET, "running", {}, MAIN, TERRA),
            ("herdr", SONNET, "completed", {"git": "herdr/x"}, MAIN, TERRA),
            ("detached", SONNET, "completed", {"git": "HEAD"}, MAIN, TERRA),
            ("shared", SONNET, "completed", {"root": True}, MAIN, TERRA),
            ("pr", SONNET, "running", {"pr": True}, PR, TERRA),
            ("build", MINIMAX, "completed", {"type": "standard"}, OWN, GLM),
        ]
        for name, model, status, kw, workspace, expected in cases:
            with self.subTest(name):
                self.cmds = []
                self.git = kw.get("git", "builder/x")
                self.root = kw.get("root", False)
                self.block(SONNET, MINIMAX)
                self.thread_on(model, status, kw.get("pr", False))
                kind = kw.get("type", "fix")
                _, ledger = self.send(task_type=kind)
                [args] = self.launches()
                want = [expected, kind, "fix it", workspace]
                self.assertEqual([args[k] for k in KEYS], want)
                self.assertEqual(list(ledger), [KEY])

    def test_unblocked_thread_is_sent_to_as_before(self):
        self.thread_on(SONNET, "completed")
        self.send()
        cmd = self.cmds[-1]
        self.assertEqual(cmd[cmd.index("--tool") + 1], "t3_thread_send")
        self.assertEqual(json.loads(cmd[2]), {"threadId": "t1", "message": "fix it"})

    def test_unblocked_running_thread_on_a_later_entry_is_held(self):
        self.thread_on(TERRA, "running")
        out, ledger = self.send()
        self.assertIn("held until it is idle", out)
        self.assertEqual((self.cmds, ledger), ([], {}))

    def test_every_fix_model_blocked_leaves_the_send_queued(self):
        self.block(SONNET, TERRA)
        self.thread_on(SONNET, "running")
        out, ledger = self.send()
        self.assertEqual(out, f"skip {KEY}: every fix model is blocked")
        self.assertEqual((self.cmds, ledger), ([], {}))

    def test_a_blocked_continuation_starts_one_replacement(self):
        self.block(SONNET)
        self.thread_on(SONNET, "running")
        ledger = {}
        for _ in range(2):
            ledger.pop("cont:t1", None)
            lane.unstick(REPO, ledger)
        self.assertEqual(len(self.launches(CONT)), 1)
        self.assertIn(CONT, ledger)

