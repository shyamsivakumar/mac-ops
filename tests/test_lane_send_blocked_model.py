"""A lane send to a thread on a blocked model starts a fresh thread instead.

The lane driver's `send` is replayed with the real models.json fix list and a
real providers-blocked.json. The coordq command it builds is recorded, so each
case reads what the queue would be handed.
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
LANE_DIR = ROOT / "coordinator" / "overnight"
REPO = "shyamsivakumar/mac-ops"
WORKTREE = "/work/builder"
MESSAGE = "fix the finding on head abc"
SONNET = {"instanceId": "claudeAgent", "model": "claude-sonnet-5-5"}
TERRA = {"instanceId": "codex", "model": "gpt-6.1-terra"}


def load_lane():
    if str(LANE_DIR) not in sys.path:
        sys.path.insert(0, str(LANE_DIR))
    if "lane_driver" in sys.modules:
        return sys.modules["lane_driver"]
    loader = SourceFileLoader("lane_driver", str(LANE_DIR / "lane_driver.py"))
    spec = importlib.util.spec_from_loader("lane_driver", loader)
    lane = importlib.util.module_from_spec(spec)
    loader.exec_module(lane)
    sys.modules["lane_driver"] = lane
    return lane


class BlockedModelSendTests(unittest.TestCase):
    def setUp(self):
        self.lane = load_lane()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(
            os.environ,
            {
                "COORDQ_DIR": tmp.name,
                "COORDINATOR_MODELS": str(ROOT / "coordinator" / "models.json"),
            },
        )
        env.start()
        self.addCleanup(env.stop)
        self.queue_dir = tmp.name
        self.commands = []

    def block(self, *identities):
        blocked = {name: {"reason": "usage limit"} for name in identities}
        with open(os.path.join(self.queue_dir, "providers-blocked.json"), "w") as f:
            json.dump({"blocked": blocked}, f)

    def send(self, thread_model, status):
        def run(cmd, timeout=150):
            self.commands.append(cmd)
            return "queued"

        thread = {
            "providerInstanceId": thread_model["instanceId"],
            "model": thread_model["model"],
            "status": status,
            "sendable": True,
            "worktreePath": WORKTREE,
        }
        ledger = {}
        with (
            patch.object(
                self.lane, "CFG", {REPO: {"key": "MO", "projectId": "fixture"}}
            ),
            patch.object(self.lane, "DRY", False),
            patch.object(self.lane, "root_workspace", return_value=False),
            patch.object(self.lane, "run", run),
            patch.object(self.lane, "t3", lambda tool, args: {"thread": thread}),
        ):
            result = self.lane.send(
                "t1", MESSAGE, "MO#1 continue", ledger, f"fix:{REPO}#1", repo=REPO
            )
        return result, ledger

    def launched(self):
        self.assertEqual(len(self.commands), 1)
        cmd = self.commands[0]
        self.assertNotIn("--tool", cmd)
        return json.loads(cmd[2])

    def test_blocked_thread_gets_a_fresh_thread_on_the_next_entry(self):
        self.block("claudeAgent:claude-sonnet-5-5")
        for status in ("completed", "running"):
            with self.subTest(status=status):
                self.commands.clear()
                _, ledger = self.send(SONNET, status)
                args = self.launched()
                self.assertEqual(args["clientRequestId"], f"fix:{REPO}#1")
                self.assertEqual(list(ledger), [f"fix:{REPO}#1"])
                self.assertEqual(args["modelSelection"], TERRA)
                self.assertEqual(args["taskType"], "fix")
                self.assertEqual(args["message"], MESSAGE)
                self.assertEqual(
                    args["workspaceStrategy"],
                    {"type": "existing_worktree", "worktreePath": WORKTREE},
                )

    def test_unblocked_thread_is_sent_to_as_before(self):
        self.send(SONNET, "completed")
        cmd = self.commands[0]
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(cmd[cmd.index("--tool") + 1], "t3_thread_send")
        self.assertEqual(json.loads(cmd[2]), {"threadId": "t1", "message": MESSAGE})

    def test_unblocked_running_thread_on_a_later_entry_is_still_held(self):
        result, ledger = self.send(TERRA, "running")
        self.assertIn("held until it is idle", result)
        self.assertEqual(self.commands, [])
        self.assertEqual(ledger, {})

    def test_every_fix_model_blocked_leaves_the_send_queued(self):
        self.block("claudeAgent:claude-sonnet-5-5", "codex:gpt-6.1-terra")
        result, ledger = self.send(SONNET, "running")
        self.assertEqual(result, f"skip fix:{REPO}#1: every fix model is blocked")
        self.assertEqual(self.commands, [])
        self.assertEqual(ledger, {})


if __name__ == "__main__":
    unittest.main()
