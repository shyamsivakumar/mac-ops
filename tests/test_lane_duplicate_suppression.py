"""Two lane passes over the same board queue each message once.

The lane driver is replayed against the real queue logic: the `coordq
start` the driver makes is handed to the loaded coordq module, and the
queue's refusal comes back to the driver as a skip. The second pass runs
with an empty ledger, because the queue is the record that has to hold
when a pass dies before it saves one.
"""

import argparse
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch

from tests.test_gatekeep_backstop_reviewer import load_coordq

ROOT = Path(__file__).resolve().parents[1]
LANE_DIR = ROOT / "coordinator" / "overnight"
REPO = "shyamsivakumar/mac-ops"
HEAD = "a" * 40
sys.path[:0] = [str(LANE_DIR), str(ROOT / "coordinator" / "bin")]
import lane_driver as lane


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.q = load_coordq()
        self.q.DIR = self.tmp.name
        self.q.cap = lambda: 6
        # The slots are full, so a queued message waits where the replay can
        # count it.
        self.q.live = lambda: 6
        self.q.save({"next": 1, "items": []})
        if str(LANE_DIR) not in sys.path:
            sys.path.insert(0, str(LANE_DIR))
        if "lane_driver" in sys.modules:
            self.lane = sys.modules["lane_driver"]
        else:
            loader = SourceFileLoader("lane_driver", str(LANE_DIR / "lane_driver.py"))
            spec = importlib.util.spec_from_loader("lane_driver", loader)
            self.lane = importlib.util.module_from_spec(spec)
            loader.exec_module(self.lane)
            sys.modules["lane_driver"] = self.lane

    def queue_start(self, cmd):
        """Hand the driver's coordq start to the real queue."""
        payload = json.loads(cmd[2])
        options = cmd[3:]
        title = options[options.index("--title") + 1] if "--title" in options else None
        tool = options[options.index("--tool") + 1] if "--tool" in options else None
        priority = int(options[options.index("--priority") + 1]) if "--priority" in options else 0
        args = argparse.Namespace(args=json.dumps(payload), title=title,
                                  priority=priority, tool=tool, action_key=None)
        err = io.StringIO()
        with patch.object(self.q, "read_rules", return_value="rules"), redirect_stderr(err):
            try:
                with redirect_stdout(io.StringIO()):
                    self.q.cmd_start(args)
            except SystemExit as exc:
                out = err.getvalue()
                raise subprocess.CalledProcessError(1, cmd, output="", stderr=out) from None
        return "queued"

    def snapshot(self, prs):
        return {"repos": {REPO: {"prs": prs, "issues": [{"number": 10, "labels": []}]}}}

    def pr(self, number=20, head=HEAD, body=None):
        body = f"Refs #10\nBuilder check: PASS {head}" if body is None else body
        return {"number": number, "state": "OPEN", "headRefOid": head, "body": body,
                "mergeable": "MERGEABLE", "isDraft": False, "statusCheckRollup": []}

    def pass_once(self, ledger, prs, verdict="FAIL", builder="live-builder",
                  status="running", reply="finding\nVERDICT: FAIL"):
        commands = []

        def run(cmd, timeout=150):
            commands.append(cmd)
            if cmd[:2] == ["gh", "pr"] and "view" in cmd:
                fields = cmd[cmd.index("--json") + 1]
                if fields == "state,mergedAt":
                    return json.dumps({"state": "OPEN", "mergedAt": None})
                return json.dumps({"number": 20, "state": "OPEN",
                                   "headRefName": "builder/fixture", "baseRefName": "main"})
            if cmd[0] == self.lane.COORDQ:
                return self.queue_start(cmd)
            raise AssertionError(f"unexpected command: {cmd}")

        def threads(tool, args):
            if tool == "t3_thread_read":
                if args.get("threadId") == "live-builder":
                    fixer = self.lane.model_list.first_available("fix")["selection"]
                    return {"thread": {"providerInstanceId": fixer["instanceId"], "model": fixer["model"],
                                       "status": status, "sendable": True}}
            raise AssertionError(f"unexpected T3 call: {tool}")

        with patch.object(self.lane, "CFG", {REPO: {"key": "MO", "projectId": "fixture"}}), \
             patch.object(self.lane, "LANE_REPOS", [REPO]), \
             patch.object(self.lane, "SNAPSHOT", self.snapshot(prs)), \
             patch.object(self.lane, "DRY", False), \
             patch.object(self.lane, "builder_thread", return_value=("10", builder)), \
             patch.object(self.lane, "gate_verdict", return_value=(verdict, {"threadId": "gate"}, reply)), \
             patch.object(self.lane, "run", run), patch.object(self.lane, "t3", threads), \
             patch.object(self.lane, "read_json", return_value={"number": 20, "state": "OPEN",
                                                               "headRefName": "builder/fixture",
                                                               "baseRefName": "main"}):
            return self.lane.act_on_pr(REPO, 20, ledger), commands

    def items(self):
        return [(item["title"], item["tool"]) for item in self.q.load()["items"]]

    def title(self, head=HEAD, action="gate findings"):
        """The title the lane gives one head's message for one pull request."""
        return f"MO#20 {action} {head}"

    def test_two_passes_over_the_same_board_queue_one_findings_message(self):
        prs = [self.pr()]
        first, _ = self.pass_once({}, prs)
        self.assertTrue(first.startswith("#20 fix: "), first)
        self.assertEqual(self.items(), [(self.title(), "t3_thread_send")])
        # The second pass has no ledger record: the queue is what holds.
        second, _ = self.pass_once({}, prs)
        self.assertIn("already holds this message", second)
        self.assertEqual(self.items(), [(self.title(), "t3_thread_send")])

    def test_a_second_head_is_not_refused_while_the_first_is_queued(self):
        # The gate finding: the message carries its head, so head B's findings
        # are not read as a copy of head A's queued ones.
        first, _ = self.pass_once({}, [self.pr(head=HEAD)])
        second, _ = self.pass_once({}, [self.pr(head="b" * 40)])
        self.assertTrue(first.startswith("#20 fix: "), first)
        self.assertTrue(second.startswith("#20 fix: "), second)
        self.assertEqual(self.items(), [(self.title(HEAD), "t3_thread_send"),
                                        (self.title("b" * 40), "t3_thread_send")])

    def test_two_heads_with_one_prefix_are_two_messages(self):
        # The gate finding: a short head prefix can be shared, so the whole
        # head is in the title. These two heads differ only in its last byte.
        first, second = "a" * 8 + "1" * 32, "a" * 8 + "2" * 32
        self.assertTrue(self.pass_once({}, [self.pr(head=first)])[0].startswith("#20 fix: "))
        after, _ = self.pass_once({}, [self.pr(head=second)])
        self.assertTrue(after.startswith("#20 fix: "), after)
        self.assertEqual(self.items(), [(self.title(first), "t3_thread_send"),
                                        (self.title(second), "t3_thread_send")])

    def test_a_message_whose_thread_finished_goes_out_again(self):
        # The builder work is done and its thread is not live, so the record
        # of the message is spent and the same message is allowed again.
        self.q.save({"next": 2, "items": [], "started": [{
            "id": 1, "title": self.title(), "target": "live-builder",
            "thread": "live-builder", "actionKey": "", "at": self.q.time.time()}]})
        with patch.object(self.q, "active_thread_ids", return_value=set()):
            again, _ = self.pass_once({}, [self.pr()])
        self.assertTrue(again.startswith("#20 fix: "), again)
        self.assertEqual(self.items(), [(self.title(), "t3_thread_send")])

    def test_a_new_head_goes_out_once_the_builder_stopped(self):
        # A head the builder is still working does not take a second copy of
        # its own message, and another head is another message either way.
        self.q.save({"next": 2, "items": [], "started": [{
            "id": 1, "title": self.title(), "target": "live-builder",
            "thread": "live-builder", "actionKey": "", "at": self.q.time.time()}]})
        with patch.object(self.q, "active_thread_ids", return_value={"live-builder"}):
            same_head, _ = self.pass_once({}, [self.pr()])
            other_head, _ = self.pass_once({}, [self.pr(head="b" * 40)])
        self.assertIn("already holds this message", same_head)
        self.assertTrue(other_head.startswith("#20 fix: "), other_head)
        self.assertEqual(self.items(), [(self.title("b" * 40), "t3_thread_send")])

    def test_findings_already_with_a_running_builder_are_not_sent_again(self):
        head = self.pr()["headRefOid"]
        ledger = {f"fix:{REPO}#20:{head}": "started #1"}
        result, commands = self.pass_once(ledger, [self.pr()], status="running")
        self.assertTrue(result.startswith("skip "), result)
        self.assertEqual([c for c in commands if c[0] == self.lane.COORDQ], [])

    def test_a_closed_pull_request_gets_no_message(self):
        pr = self.pr(body="Refs #10")
        pr["state"] = "CLOSED"
        result, commands = self.pass_once({}, [pr])
        self.assertIsNone(result)
        self.assertEqual([c for c in commands if c[0] == self.lane.COORDQ], [])

    def test_a_superseded_pull_request_gets_no_message(self):
        # A newer pull request for the same ticket carries the work now.
        prs = [self.pr(number=20), self.pr(number=21, head="c" * 40)]
        result, commands = self.pass_once({}, prs)
        self.assertTrue(result.startswith("skip #20: superseded"), result)
        self.assertEqual([c for c in commands if c[0] == self.lane.COORDQ], [])


WT = "/work/builder"
SELECTIONS = {
    "sonnet": {"instanceId": "claudeAgent", "model": "claude-sonnet-5-5"},
    "terra": {"instanceId": "codex", "model": "gpt-6.1-terra"},
    "minimax": {"instanceId": "minimax", "model": "minimax/MiniMax-M3.1-Flash"},
    "glm": {"instanceId": "glm", "model": "zai/glm-5.3"},
}
OWN = {"type": "existing_worktree", "worktreePath": WT}
MAIN = {"type": "worktree", "baseRef": "origin/main", "startFromOrigin": True}


class BlockedModelSendTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cmds, self.git, self.root, self.dir = [], "builder/x", False, tmp.name
        receipts = Path(tmp.name, "receipts.json")
        receipts.write_text(json.dumps({f"ticket:{REPO}#9:a1": "t1"}))
        env = {"COORDQ_DIR": tmp.name, "COORDINATOR_MODELS": str(ROOT / "coordinator" / "models.json")}
        issues = {"repos": {REPO: {"issues": [{"number": 9, "labels": []}], "prs": []}}}

        def run(cmd, timeout=150):
            self.cmds.append(cmd)
            return self.git if cmd[0] == "git" else "queued"

        for patcher in (
            patch.dict("os.environ", env),
            patch.object(lane, "CFG", {REPO: {"key": "MO", "projectId": "p"}}),
            patch.object(lane, "RECEIPTS", str(receipts)),
            patch.object(lane, "SNAPSHOT", issues),
            patch.object(lane, "DRY", False),
            patch.object(lane, "root_workspace", lambda thread: self.root),
            patch.object(lane, "pr_action_skip", return_value=({"headRefName": "builder/pr"}, None)),
            patch.object(lane, "run", run),
            patch.object(lane, "t3", lambda tool, args: {"thread": self.thread}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def thread_on(self, name, status, blocked=(), attached=False):
        selection = SELECTIONS[name]
        names = {lane.model_list.identity(SELECTIONS[b]): {"reason": "limit"} for b in blocked}
        Path(self.dir, "providers-blocked.json").write_text(json.dumps({"blocked": names}))
        pulls = [{"repository": REPO, "number": 7}] * attached
        self.thread = {"sendable": True, "worktreePath": WT, **selection, "providerInstanceId": selection["instanceId"],
                       "status": status, "pullRequests": pulls}

    def launches(self, key):
        starts = [json.loads(c[2]) for c in self.cmds if c[0] == lane.COORDQ]
        return [a for a in starts if a.get("clientRequestId") == key]

    def test_blocked_thread_is_replaced_on_the_next_entry(self):
        key = f"fix:{REPO}#1"
        cases = [("idle", "sonnet", "completed", {}, OWN, "terra", "fix"),
                 ("running", "sonnet", "running", {}, MAIN, "terra", "fix"),
                 ("herdr", "sonnet", "completed", {"git": "herdr/x"}, MAIN, "terra", "fix"),
                 ("detached", "sonnet", "completed", {"git": "HEAD"}, MAIN, "terra", "fix"),
                 ("shared", "sonnet", "completed", {"root": True}, MAIN, "terra", "fix"),
                 ("pr", "sonnet", "running", {"pr": True}, {**MAIN, "baseRef": "origin/builder/pr"}, "terra", "fix"),
                 ("build", "minimax", "completed", {}, OWN, "glm", "standard")]
        for name, model, status, kw, workspace, expected, kind in cases:
            with self.subTest(name):
                self.cmds, self.git, self.root = [], kw.get("git", "builder/x"), kw.get("root", False)
                self.thread_on(model, status, ("sonnet", "minimax"), kw.get("pr", False))
                ledger = {}
                lane.send("t1", "fix it", "t", ledger, key, repo=REPO, task_type=kind)
                [args] = self.launches(key)
                self.assertEqual([args[k] for k in ("modelSelection", "taskType", "message", "workspaceStrategy")],
                                 [SELECTIONS[expected], kind, "fix it", workspace])
                self.assertIn(key, ledger)

    def test_unblocked_send_and_all_blocked_queue(self):
        key = f"fix:{REPO}#1"
        self.thread_on("terra", "completed")
        lane.send("t1", "fix it", "t", {}, key, repo=REPO)
        cmd = self.cmds[-1]
        self.assertEqual(cmd[cmd.index("--tool") + 1], "t3_thread_send")
        self.assertEqual(json.loads(cmd[2]), {"threadId": "t1", "message": "fix it"})
        self.cmds = []
        self.thread_on("sonnet", "running", ("sonnet", "terra"))
        ledger = {}
        out = lane.send("t1", "fix it", "t", ledger, key, repo=REPO)
        self.assertEqual((out, self.cmds, ledger), (f"skip {key}: every fix model is blocked", [], {}))

    def test_continuations_keep_a_key_only_for_a_blocked_replacement(self):
        key = f"continue:{REPO}#9:t1"
        for label, blocked, replacements in (("blocked", ("sonnet",), 1), ("later", (), 2)):
            with self.subTest(label):
                self.cmds, ledger = [], {}
                self.thread_on("sonnet", "completed", blocked)
                for _ in range(2):
                    ledger.pop("cont:t1", None)
                    lane.unstick(REPO, ledger)
                self.assertEqual(len(self.launches(key)), replacements)
                self.assertEqual(key in ledger, bool(blocked))
                self.thread_on("sonnet", "completed")
                ledger.pop("cont:t1", None)
                lane.unstick(REPO, ledger)
                self.assertEqual((len(self.launches(key)), key in ledger), (replacements + 1, False))

    def test_two_replacements_never_share_one_worktree(self):
        self.thread_on("sonnet", "completed", ("sonnet",))
        ledger = {}
        for key in (f"fix:{REPO}#1", f"fix:{REPO}#2"):
            lane.send("t1", "fix it", "t", ledger, key, repo=REPO)
        workspaces = [json.loads(c[2])["workspaceStrategy"] for c in self.cmds if c[0] == lane.COORDQ]
        self.assertEqual(workspaces, [OWN, MAIN])


if __name__ == "__main__":
    unittest.main()
