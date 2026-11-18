"""Prompt, skill and playbook changes never auto-merge (Refs #543).

One path list decides it, and two places read it: the gate brief built by
`ticket gate`, and the lane driver that merges a passing pull request. The
tests here pin the list and both call sites.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_check_proof import load

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "coordinator" / "bin"
OVERNIGHT = ROOT / "coordinator" / "overnight"
# `ticket`, `gate_policy` and `lane_driver` import their neighbours by bare
# name, the way they run from the installed bin directory.
for folder in (BIN, OVERNIGHT):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import prompt_paths  # noqa: E402


class PromptPathTest(unittest.TestCase):
    """The paths that stop a pull request at the verdict."""

    def test_the_prompt_paths_are_prompt_paths(self):
        for path in ("AGENT-RULES.md",
                     "coordinator/config/AGENT-RULES.md",
                     "coordinator/bin/gate_bar.py",
                     "coordinator/bin/gate_policy.py",
                     "coordinator/overnight/playbook.md",
                     "coordinator/config/agents/code-reviewer.md",
                     "skills/animate/SKILL.md",
                     "runtime/codex/skills/animate/SKILL.md",
                     "prompts/builder.md"):
            with self.subTest(path=path):
                self.assertTrue(prompt_paths.is_prompt_path(path))

    def test_runtime_code_is_not_a_prompt_path(self):
        for path in ("coordinator/bin/ticket",
                     "coordinator/overnight/lane_driver.py",
                     "coordinator/bin/gate_reviewers.py",
                     "scripts/mac_ops_fast_check.py",
                     "docs/ticket-gate.md",
                     "evidence/MO-543/check-proof.md",
                     "tests/test_prompt_paths.py",
                     "",
                     None):
            with self.subTest(path=path):
                self.assertFalse(prompt_paths.is_prompt_path(path))

    def test_one_prompt_path_is_enough(self):
        self.assertTrue(prompt_paths.prompt_change(
            ["coordinator/bin/ticket", "coordinator/config/AGENT-RULES.md"]))
        self.assertFalse(prompt_paths.prompt_change(["coordinator/bin/ticket"]))

    def test_an_unreadable_list_adds_no_hold(self):
        """An unknown list is never a prompt change: it must not block a merge."""
        self.assertFalse(prompt_paths.prompt_change(None))
        self.assertFalse(prompt_paths.prompt_change([]))

    def test_a_skills_directory_at_the_top_counts(self):
        self.assertTrue(prompt_paths.is_prompt_path("skills/SKILL.md"))
        self.assertTrue(prompt_paths.is_prompt_path("prompts/x.md"))


class GateBriefTest(unittest.TestCase):
    """The gate brief says do not merge, in place of the merge order."""

    def brief(self, **kwargs):
        gate_policy = load(BIN / "gate_policy.py", "gate_policy")
        return gate_policy.build_gate_brief(
            {"key": "MO"}, "shyamsivakumar/mac-ops", 543, 544, "a" * 40, False,
            proof="| syntax | passed |", proof_path="evidence/MO-543/check-proof.md",
            proof_state="found", **kwargs)

    def test_a_prompt_change_gets_no_merge_order(self):
        text = self.brief(prompt=True)
        self.assertIn("never auto-merges", text)
        self.assertIn("do not merge", text)
        self.assertNotIn("gh pr merge", text)
        self.assertIn("review only", text)

    def test_a_prompt_change_closes_no_issue(self):
        text = self.brief(prompt=True)
        self.assertNotIn("gh issue close", text)

    def test_code_only_keeps_the_merge_order(self):
        text = self.brief(prompt=False)
        self.assertIn("gh pr merge 544 -R shyamsivakumar/mac-ops --squash", text)
        self.assertNotIn("never auto-merges", text)
        self.assertIn("review and merge", text)

    def test_the_verdict_lines_are_the_same_either_way(self):
        for prompt in (True, False):
            with self.subTest(prompt=prompt):
                text = self.brief(prompt=prompt)
                self.assertIn("CHECK: PASS " + "a" * 40, text)
                self.assertIn("VERDICT: PASS", text)


class TicketGateTest(unittest.TestCase):
    """`ticket gate` reads the pull request's paths through the list."""

    def setUp(self):
        self.ticket = load(BIN / "ticket", "ticket")

    def prompt_pull(self, paths):
        with patch.object(self.ticket, "pull_files", return_value=paths):
            return self.ticket.prompt_pull("shyamsivakumar/mac-ops", 544, None)

    def test_a_prompt_pull_request_is_held(self):
        self.assertTrue(self.prompt_pull(["coordinator/config/AGENT-RULES.md"]))

    def test_a_code_pull_request_is_not_held(self):
        self.assertFalse(self.prompt_pull(["coordinator/bin/ticket", "docs/ticket-gate.md"]))

    def test_an_unreadable_list_is_not_held(self):
        self.assertFalse(self.prompt_pull(None))


class CoordqGateTest(unittest.TestCase):
    """The queue's own gatekeep builds the same held brief."""

    REPO = "shyamsivakumar/fixture"
    HEAD = "a" * 40

    def setUp(self):
        from tests.test_gatekeep_backstop_reviewer import load_coordq
        self.coordq = load_coordq()

    def test_the_queue_reads_the_same_list(self):
        with patch.object(self.coordq, "gh_json",
                          return_value=[{"filename": "coordinator/config/AGENT-RULES.md"}]):
            self.assertTrue(self.coordq.gate_prompt_change("shyamsivakumar/mac-ops", 544))
        with patch.object(self.coordq, "gh_json",
                          return_value=[{"filename": "coordinator/bin/ticket"}]):
            self.assertFalse(self.coordq.gate_prompt_change("shyamsivakumar/mac-ops", 544))

    def test_a_failed_read_is_not_a_hold(self):
        with patch.object(self.coordq, "gh_json", side_effect=RuntimeError("boom")):
            self.assertFalse(self.coordq.gate_prompt_change("shyamsivakumar/mac-ops", 544))

    def test_the_queued_brief_says_do_not_merge(self):
        settings = {"key": "MO", "projectId": "fixture"}
        model = {"instanceId": "codex", "model": "gpt-6.2-astra"}
        args = self.coordq.gate_args(settings, "shyamsivakumar/mac-ops", 543, 544,
                                     "a" * 40, False, model, prompt=True)
        self.assertIn("never auto-merges", args["message"])
        self.assertNotIn("gh pr merge", args["message"])
        code = self.coordq.gate_args(settings, "shyamsivakumar/mac-ops", 543, 544,
                                     "a" * 40, False, model)
        self.assertIn("gh pr merge 544 -R shyamsivakumar/mac-ops", code["message"])

    def gatekeep(self, changed):
        """The gate the queue's own gatekeeper would queue, for one file list."""
        import types
        from contextlib import redirect_stderr
        import io
        import json
        coordq = self.coordq
        head = self.HEAD
        repo = self.REPO
        pull = {"draft": False, "number": 7, "head": {"sha": head},
                "body": f"Refs #9\nBuilder check: PASS {head}\n"}
        receipt = {"kind": "receipt", "attempt": 1, "requestId": "req-1"}
        comment = {"user": {"login": "me"},
                   "body": "attempt 1\n<!-- coordinator-ticket " + json.dumps(receipt) + " -->"}

        def fake_gh(endpoint):
            if "/files" in endpoint:
                return [{"filename": path} for path in changed]
            if endpoint.startswith(f"repos/{repo}/pulls"):
                return [dict(pull)]
            if endpoint.endswith("/comments?per_page=100"):
                return [comment]
            if endpoint.startswith(f"repos/{repo}/commits/"):
                return []
            raise AssertionError(f"unexpected endpoint {endpoint}")

        quiet = types.SimpleNamespace(returncode=0, stdout="me\n", stderr="")
        with patch.object(coordq, "subprocess", types.SimpleNamespace(run=lambda *a, **k: quiet)), \
                patch.object(coordq, "gh_json", fake_gh), \
                patch.object(coordq, "load_receipts", return_value={"req-1": "thread-1"}), \
                patch.object(coordq, "read_builder_thread",
                             return_value=({"providerInstanceId": "codex", "model": "gpt-6.2-astra"}, [])), \
                patch.object(coordq, "builder_thread_for_issue", return_value="thread-1"), \
                patch("builtins.open", side_effect=AssertionError("live filesystem forbidden")), \
                redirect_stderr(io.StringIO()):
            events = list(coordq.gate_candidates({"repos": {repo: {"key": "T", "projectId": "P"}}}))
        messages = [event["args"]["message"] for event in events if event["kind"] == "candidate"]
        self.assertEqual(len(messages), 1)
        return messages[0]

    def test_the_gatekeep_queues_a_held_gate(self):
        message = self.gatekeep(["coordinator/config/AGENT-RULES.md"])
        self.assertIn("never auto-merges", message)
        self.assertNotIn("gh pr merge", message)

    def test_the_gatekeep_queues_a_mergeable_gate_for_code(self):
        message = self.gatekeep(["coordinator/bin/ticket"])
        self.assertIn("gh pr merge 7 -R shyamsivakumar/fixture --squash", message)
        self.assertNotIn("never auto-merges", message)


class LanePassTest(unittest.TestCase):
    """A passing prompt pull request writes one item and merges nothing."""

    def setUp(self):
        import lane_driver
        self.lane = lane_driver
        self.saved_cfg = lane_driver.CFG
        lane_driver.CFG = {"shyamsivakumar/mac-ops": {"key": "MO", "projectId": "fixture"}}
        self.addCleanup(lambda: setattr(lane_driver, "CFG", self.saved_cfg))
        self.item = self.lane.prompt_merge_item("shyamsivakumar/mac-ops", 544, "a" * 40)

    def test_the_item_is_one_action_for_shyam(self):
        self.assertEqual(self.item["id"], "prompt-merge-MO-544")
        self.assertEqual(self.item["group"], "Coordinator")
        self.assertEqual(self.item["kind"], "action")
        self.assertNotIn("options", self.item)
        self.assertIn("gh pr merge 544 -R shyamsivakumar/mac-ops", self.item["why"])

    def test_the_lane_reads_the_same_list(self):
        with patch.object(self.lane, "run", return_value='[{"filename": "skills/x/SKILL.md"}]'):
            self.assertTrue(self.lane.prompt_pull("shyamsivakumar/mac-ops", 544))
        with patch.object(self.lane, "run", return_value='[{"filename": "coordinator/bin/ticket"}]'):
            self.assertFalse(self.lane.prompt_pull("shyamsivakumar/mac-ops", 544))

    def test_it_publishes_under_the_board_lock(self):
        calls = []

        def board_update(path, alarm_id, action, item=None, attempts=5):
            calls.append((path, alarm_id, action, item))
            return "wrote"

        with patch.object(self.lane.alarms, "board_update", board_update):
            self.assertEqual(self.lane.publish_decision(self.item), "wrote")
        self.assertEqual(calls, [(self.lane.DECISIONS_PATH, "prompt-merge-MO-544", "raise", self.item)])


if __name__ == "__main__":
    unittest.main()
