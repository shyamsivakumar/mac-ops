"""Every lane launch and send runs on the first unblocked builder (MO-1094).

The replay of the cases the coordinator named for the re-cut of #537: with
no preference and nothing blocked the choice is the first entry of the
build list, a ticket's builder label comes first, a blocked provider is
skipped, a thread that runs no builder takes no send, no send goes to a
thread that works in the shared root of a repository, and a gate that
ended without a verdict is not a builder failure.

The model list is the file in the checkout, so the test never reads the
installed one.
"""

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import mock_open, patch

ROOT = Path(__file__).resolve().parents[1]
OVERNIGHT = ROOT / "coordinator" / "overnight"
MODELS = ROOT / "coordinator" / "models.json"
REPO = "shyamsivakumar/mac-ops"
HEAD = "a" * 40
MINIMAX = {"instanceId": "minimax", "model": "minimax/MiniMax-M3.1-Flash"}
GLM = {"instanceId": "glm", "model": "zai/glm-5.3"}
SOL = {"instanceId": "codex", "model": "gpt-6.1-sol"}


def load_lane():
    """The lane driver as a module, reading the model list of the checkout."""
    for folder in (str(OVERNIGHT), str(ROOT / "coordinator" / "bin")):
        if folder not in sys.path:
            sys.path.insert(0, folder)
    loader = SourceFileLoader("lane_driver_builder_choice", str(OVERNIGHT / "lane_driver.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class BuilderChoice(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.previous = os.environ.get("COORDQ_DIR")
        os.environ["COORDQ_DIR"] = self.scratch.name

        def restore():
            if self.previous is None:
                os.environ.pop("COORDQ_DIR", None)
            else:
                os.environ["COORDQ_DIR"] = self.previous
        self.addCleanup(restore)
        self.lane = load_lane()
        self.lane.DRY = False
        self.lane.CFG = {REPO: {"projectId": "fixture", "key": "MO"}}

    def block(self, *identities):
        """Record the blocked providers the model list reads."""
        path = Path(self.scratch.name) / "providers-blocked.json"
        path.write_text(json.dumps({"blocked": {identity: {"reason": "usage limit"} for identity in identities}}))

    def launch(self, thread, issue=None, builder_label=None, pr=True, root_workspace=False):
        """Replay one send and return the dispatch payload, or None."""
        calls = []

        def run(cmd, timeout=150):
            calls.append(cmd)
            return "#1 p0 started"

        snapshot = {"tickets": [], "repos": {REPO: {"prs": [], "issues": [
            {"number": 10, "labels": ([{"name": f"builder:{builder_label}"}] if builder_label else [])}]}}}
        with patch.dict(os.environ, {"COORDINATOR_MODELS": str(MODELS)}), \
             patch.object(self.lane, "t3", lambda tool, args: {"thread": thread}), \
             patch.object(self.lane, "run", run), \
             patch.object(self.lane, "root_workspace", return_value=root_workspace), \
             patch.object(self.lane, "branch_on_origin", return_value=True), \
             patch.object(self.lane, "SNAPSHOT", snapshot), \
             patch.object(self.lane, "read_json", return_value={"number": 20, "state": "OPEN",
                                                               "headRefName": "builder/fixture",
                                                               "baseRefName": "main"}), \
             redirect_stdout(io.StringIO()):
            out = self.lane.send("old", "Continue the work.", "MO#20 continue", {},
                                 f"fix:{REPO}#20:{HEAD}", repo=REPO, pr_number=20 if pr else None,
                                 issue=issue)
        if not calls:
            return out, None
        return out, json.loads(calls[0][2])

    def thread(self, model, **fields):
        record = {"threadId": "old", "status": "completed", "providerInstanceId": model["instanceId"],
                  "model": model["model"], "worktreePath": "/fixture/worktree", "pullRequests": []}
        record.update(fields)
        return record

    def test_with_no_preference_and_nothing_blocked_the_choice_is_the_first_entry(self):
        out, payload = self.launch(self.thread(SOL))
        self.assertEqual(payload["modelSelection"], MINIMAX)
        self.assertNotIn("threadId", payload)
        self.assertIn("fresh", out)

    def test_the_ticket_builder_label_comes_first(self):
        out, payload = self.launch(self.thread(SOL), issue=10, builder_label="glm")
        self.assertEqual(payload["modelSelection"], GLM)

    def test_a_thread_on_another_builder_takes_no_send(self):
        # The ticket names glm, so a minimax thread does not take the work.
        out, payload = self.launch(self.thread(MINIMAX), issue=10, builder_label="glm")
        self.assertNotIn("threadId", payload)
        self.assertEqual(payload["modelSelection"], GLM)
        self.assertEqual(payload["workspaceStrategy"],
                         {"type": "existing_worktree", "worktreePath": "/fixture/worktree"})

    def test_a_thread_on_the_second_builder_takes_no_send(self):
        # With no preference the first entry of the list is the builder,
        # so a glm thread does not take the work either.
        out, payload = self.launch(self.thread(GLM))
        self.assertNotIn("threadId", payload)
        self.assertEqual(payload["modelSelection"], MINIMAX)

    def test_a_blocked_provider_is_never_launched_on(self):
        self.block("minimax:MiniMax-M3.1-Flash")
        out, payload = self.launch(self.thread(SOL))
        self.assertEqual(payload["modelSelection"], GLM)

    def test_a_blocked_ticket_builder_is_skipped_for_the_next_one(self):
        self.block("glm:glm-5.3")
        out, payload = self.launch(self.thread(SOL), issue=10, builder_label="glm")
        self.assertEqual(payload["modelSelection"], MINIMAX)

    def test_a_legacy_sol_thread_takes_no_send(self):
        out, payload = self.launch(self.thread(SOL))
        self.assertNotIn("threadId", payload)
        self.assertEqual(payload["workspaceStrategy"],
                         {"type": "existing_worktree", "worktreePath": "/fixture/worktree"})

    def test_a_thread_that_works_in_the_shared_root_takes_no_send(self):
        out, payload = self.launch(self.thread(MINIMAX), root_workspace=True)
        self.assertNotIn("threadId", payload)
        self.assertEqual(payload["workspaceStrategy"],
                         {"type": "worktree", "baseRef": "origin/builder/fixture", "startFromOrigin": True})

    def test_a_builder_thread_takes_the_send(self):
        out, payload = self.launch(self.thread(MINIMAX))
        self.assertEqual(payload, {"threadId": "old", "message": "Continue the work."})

    def test_every_builder_blocked_queues_nothing(self):
        self.block("minimax:MiniMax-M3.1-Flash", "glm:glm-5.3", "pi:deepseek-flash",
                   "cursor:default", "codex:gpt-6.1-terra")
        out, payload = self.launch(self.thread(SOL))
        self.assertIsNone(payload)
        self.assertIn("every builder is blocked", out)


class DeadRunChoice(unittest.TestCase):
    """A dead run relaunches on the first unblocked builder."""

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.previous = os.environ.get("COORDQ_DIR")
        os.environ["COORDQ_DIR"] = self.scratch.name
        self.lane = load_lane()
        self.lane.DRY = False
        self.lane.CFG = {REPO: {"projectId": "fixture", "key": "MO"}}

    def relaunch(self, model, messages, builder_label=None):
        """Replay one dead run and return the model of the relaunch."""
        thread = {"threadId": "fixture-dead", "title": "MO-7 build", "settled": False,
                  "providerInstanceId": model["instanceId"], "model": model["model"],
                  "worktreePath": "/fixture/worktree", "pullRequests": []}
        launches = []

        def t3(tool, args):
            if tool == "t3_thread_list":
                return {"threads": [thread]} if args.get("statuses") == ["failed", "interrupted"] else {"threads": []}
            if tool == "t3_thread_read" and args.get("view") == "messages":
                return {"items": messages}
            if tool == "t3_thread_read":
                return {"thread": thread}
            if tool == "t3_thread_organize":
                return {}
            raise AssertionError(f"unexpected T3 call {tool}")

        def run(cmd, timeout=150):
            if cmd[0] == "git":
                return "worktree /fixture/worktree\n"
            launches.append(json.loads(cmd[2]))
            return "fixture-relaunch"

        snapshot = {"tickets": [], "repos": {REPO: {"prs": [], "issues": [
            {"number": 7, "labels": ([{"name": f"builder:{builder_label}"}] if builder_label else [])}]}}}
        with patch.dict(os.environ, {"COORDINATOR_MODELS": str(MODELS)}), \
             patch.object(self.lane, "LANE_REPOS", [REPO]), \
             patch.object(self.lane, "SNAPSHOT", snapshot), \
             patch.object(self.lane, "t3", side_effect=t3), \
             patch.object(self.lane, "stall_receipts", return_value={f"ticket:{REPO}#7:a1": "fixture-dead"}), \
             patch.object(self.lane, "read_json", return_value={"state": "OPEN"}), \
             patch.object(self.lane, "run", side_effect=run), redirect_stdout(io.StringIO()):
            self.lane.recover_dead_runs({})
        return launches[0]["modelSelection"] if launches else None

    def test_a_dead_run_relaunches_on_the_first_builder(self):
        self.assertEqual(self.relaunch(MINIMAX, []), MINIMAX)

    def test_the_ticket_builder_label_comes_first(self):
        self.assertEqual(self.relaunch(MINIMAX, [], builder_label="glm"), GLM)

    def test_a_gate_that_ended_without_a_verdict_is_not_a_builder_failure(self):
        # The thread talked, the provider did not fail: the builder is not
        # treated as failed, so the relaunch runs on it again.
        messages = [{"type": "assistant_message",
                     "text": "the gate ended without a verdict; its quota was never read"}]
        self.assertEqual(self.relaunch(MINIMAX, messages), MINIMAX)

    def test_a_provider_failure_names_the_builder_as_out(self):
        messages = [{"type": "provider_error", "text": "429 rate limit reached"}]
        self.assertEqual(self.relaunch(MINIMAX, messages), GLM)


class CompletedGate(unittest.TestCase):
    """A gate that ended without a verdict is not a builder failure.

    The gate is retried once on the same head and then parks as
    needs-you. The builder takes no message and no thread: a gate that
    ended without a verdict says nothing about the builder.
    """

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.previous = os.environ.get("COORDQ_DIR")
        os.environ["COORDQ_DIR"] = self.scratch.name

        def restore():
            if self.previous is None:
                os.environ.pop("COORDQ_DIR", None)
            else:
                os.environ["COORDQ_DIR"] = self.previous
        self.addCleanup(restore)
        self.lane = load_lane()
        self.lane.DRY = False

    def replay(self, ledger):
        """Two lane passes over a pull request whose gate ended without a verdict."""
        lane = self.lane
        head = "a" * 40
        pr = {"number": 20, "state": "OPEN", "headRefOid": head, "mergeable": "MERGEABLE",
              "isDraft": False, "statusCheckRollup": [],
              "body": f"Refs #10\nBuilder check: PASS {head}"}
        snapshot = {"tickets": [], "repos": {REPO: {"prs": [pr], "issues": [{"number": 10, "labels": []}]}}}
        builder = {"threadId": "builder", "status": "completed",
                   "providerInstanceId": MINIMAX["instanceId"], "model": MINIMAX["model"],
                   "worktreePath": "/fixture/worktree", "pullRequests": []}
        gate = {"threadId": "gate", "status": "completed", "updatedAt": "fixture"}
        launches = []

        def t3(tool, args):
            if tool == "t3_thread_list":
                return {"threads": [gate]}
            if tool == "t3_thread_read" and args.get("view") == "messages":
                return {"items": [{"type": "assistant_message",
                                   "text": "the gate ended without a verdict"}]}
            if tool == "t3_thread_read":
                return {"thread": builder}
            raise AssertionError(f"unexpected T3 call {tool}")

        def run(cmd, timeout=150):
            if cmd[:2] == ["ticket", "gate"]:
                if "--print-model" in cmd:
                    return json.dumps([{"id": "astra-sub", "vendor": "openai",
                                       "selection": {"instanceId": "codex", "model": "gpt-6.2-astra"}}])
                return f"Gate exact head {head}"
            if cmd[:3] == ["gh", "pr", "view"]:
                return json.dumps({"state": "OPEN", "mergedAt": None})
            if cmd[:2] == [lane.COORDQ, "start"]:
                launches.append(json.loads(cmd[2]))
                return "fixture-receipt"
            raise AssertionError(f"unexpected command: {cmd}")

        with patch.dict(os.environ, {"COORDINATOR_MODELS": str(MODELS)}), \
             patch.object(lane, "CFG", {REPO: {"projectId": "fixture", "key": "MO"}}), \
             patch.object(lane, "SNAPSHOT", snapshot), patch.object(lane, "DRY", False), \
             patch.object(lane, "builder_thread", return_value=("10", "builder")), \
             patch.object(lane, "root_workspace", return_value=False), \
             patch.object(lane, "read_json", return_value={"number": 20, "state": "OPEN",
                                                           "headRefName": "builder/fixture",
                                                           "baseRefName": "main"}), \
             patch.object(lane, "run", run), patch.object(lane, "t3", t3), \
             redirect_stdout(io.StringIO()):
            first = lane.act_on_pr(REPO, 20, ledger)
            second = lane.act_on_pr(REPO, 20, ledger)
        return first, second, launches

    def test_a_completed_gate_without_a_verdict_is_not_a_builder_failure(self):
        first, second, launches = self.replay({})
        # One gate for the head: the retry. No second one.
        self.assertEqual(len(launches), 1)
        self.assertEqual(launches[0]["taskType"], "review")
        self.assertIn("regate", launches[0]["clientRequestId"])
        # The builder takes no message and no thread: the gate that ended
        # without a verdict is not a failure of the builder.
        self.assertNotIn("threadId", launches[0])
        self.assertTrue(second.startswith("#20: needs-you"), second)
        self.assertIn("regate", first)


class UnstickBuilders(unittest.TestCase):
    """Every unstuck ticket runs on the builder it resolves to.

    Two tickets that name different builders never share one thread, so
    the unstick groups the tickets by the builder they resolve to.
    """

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.previous = os.environ.get("COORDQ_DIR")
        os.environ["COORDQ_DIR"] = self.scratch.name

        def restore():
            if self.previous is None:
                os.environ.pop("COORDQ_DIR", None)
            else:
                os.environ["COORDQ_DIR"] = self.previous
        self.addCleanup(restore)
        self.lane = load_lane()
        self.lane.DRY = False
        self.lane.CFG = {REPO: {"projectId": "fixture", "key": "MO"}}

    def unstick(self, labels, passes=1):
        """Replay the unstick path over the given tickets and their labels."""
        lane = self.lane
        issues = [{"number": number, "labels": [{"name": f"builder:{label}"}]}
                  for number, label in labels.items()]
        snapshot = {"tickets": [], "repos": {REPO: {"prs": [], "issues": issues}}}
        launches = []

        def files(path, *args, **kwargs):
            if str(path).endswith("providers-blocked.json"):
                return mock_open(read_data='{"blocked": {}}')()
            if str(path).endswith("models.json"):
                return mock_open(read_data=MODELS.read_text())()
            if path == lane.RECEIPTS:
                return mock_open(read_data="{}")()
            return mock_open(read_data="unstick {list} in {repo}")()

        def run(cmd, timeout=150):
            launches.append(json.loads(cmd[2]))
            return "fixture-receipt"

        ledger = {}
        with patch.dict(os.environ, {"COORDINATOR_MODELS": str(MODELS)}), \
             patch.object(lane, "SNAPSHOT", snapshot), \
             patch.object(lane, "run", run), \
             patch("builtins.open", files), redirect_stdout(io.StringIO()):
            for _ in range(passes):
                lane.unstick(REPO, ledger)
        return launches, ledger

    def test_two_tickets_with_different_builders_get_their_own(self):
        launches, ledger = self.unstick({11: "glm", 12: "minimax"}, passes=2)
        self.assertEqual(len(launches), 2)
        self.assertEqual([launch["modelSelection"] for launch in launches], [GLM, MINIMAX])
        self.assertIn("#11", launches[0]["message"])
        self.assertIn("#12", launches[1]["message"])
        self.assertNotIn("#12", launches[0]["message"])
        self.assertNotIn("#11", launches[1]["message"])

    def test_two_tickets_with_the_same_builder_share_a_batch(self):
        launches, ledger = self.unstick({11: "glm", 12: "glm"}, passes=1)
        self.assertEqual(len(launches), 1)
        self.assertEqual(launches[0]["modelSelection"], GLM)
        self.assertIn("#11", launches[0]["message"])
        self.assertIn("#12", launches[0]["message"])


if __name__ == "__main__":
    unittest.main()
