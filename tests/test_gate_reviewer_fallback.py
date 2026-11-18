"""Tests for the gate reviewer fallback and the blocked reviewers.

A gate that ends without a verdict moves down the reviewer chain, once per
reviewer, and waits when the chain is exhausted. A reviewer that fails for a
blocking provider reason is blocked for every head, so every new gate starts
on the next reviewer until it recovers.

The payload in `fixtures/gate/openai_api_no_credits.json` is a recorded gate
thread: the OpenAI API ran out of credits and the run failed without an
answer and without an error text, so the fallback cannot wait for the error
to be readable.
"""
import argparse
import importlib.util
import io
import json
import os
import tempfile
import time
import types
import unittest
from contextlib import redirect_stdout
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys_path = str(ROOT / "coordinator" / "bin")
if sys_path not in os.sys.path:
    os.sys.path.insert(0, sys_path)

import gate_reviewers  # noqa: E402

REPO = "o/r"
HEAD = "a" * 40
CONFIG = {"repos": {REPO: {"key": "T", "projectId": "P"}}}
RECORDED = json.loads((ROOT / "tests" / "fixtures" / "gate" / "openai_api_no_credits.json").read_text())
API_REVIEWER = {"instanceId": "openai-api", "model": "openai/gpt-6.2-astra"}
CODEX_REVIEWER = {"instanceId": "codex", "model": "gpt-6.2-astra"}

coordq = None
QUEUE_DIR = None
SAVED_COORDQ_DIR = None


def load_coordq():
    path = ROOT / "coordinator" / "bin" / "coordq"
    loader = SourceFileLoader("coordq_reviewer_fallback", str(path))
    spec = importlib.util.spec_from_loader("coordq_reviewer_fallback", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def load_ticket():
    path = ROOT / "coordinator" / "bin" / "ticket"
    loader = SourceFileLoader("ticket_reviewer_fallback", str(path))
    spec = importlib.util.spec_from_loader("ticket_reviewer_fallback", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def setUpModule():
    global coordq, QUEUE_DIR, SAVED_COORDQ_DIR
    SAVED_COORDQ_DIR = os.environ.get("COORDQ_DIR")
    QUEUE_DIR = tempfile.mkdtemp(prefix="coordq-reviewer-fallback-")
    os.environ["COORDQ_DIR"] = QUEUE_DIR
    coordq = load_coordq()


def tearDownModule():
    if SAVED_COORDQ_DIR is None:
        os.environ.pop("COORDQ_DIR", None)
    else:
        os.environ["COORDQ_DIR"] = SAVED_COORDQ_DIR


class FakeRun:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class FallbackBase(unittest.TestCase):
    def setUp(self):
        self.saved = {name: getattr(coordq, name)
                      for name in ("gh_json", "load_receipts", "read_builder_thread",
                                   "router_chain", "subprocess", "call", "gate_request")}
        self.addCleanup(lambda: [setattr(coordq, name, value)
                                  for name, value in self.saved.items()])
        self.pr = {"draft": False, "number": 7, "head": {"sha": HEAD},
                   "body": f"Refs #9\nBuilder check: PASS {HEAD}\n"}
        self.key = f"gate:{REPO}#7:{HEAD}"
        gate_reviewers.save_blocked({})
        coordq.subprocess = types.SimpleNamespace(run=lambda *a, **k: FakeRun("me\n"))
        coordq.load_receipts = lambda: {"ticket:o/r#9:a1": "builder-1", self.key: "gate-1"}
        coordq.read_builder_thread = lambda thread_id: (
            {"providerInstanceId": "minimax", "model": "minimax/MiniMax-M3.1-Flash"},
            [{"executedModel": "minimax/MiniMax-M3.1-Flash"}])
        coordq.router_chain = lambda route: []
        coordq.gh_json = self.fake_gh
        self.config = os.path.join(QUEUE_DIR, "gatekeep-config.json")
        with open(self.config, "w") as f:
            json.dump(CONFIG, f)

    def fake_gh(self, endpoint):
        if endpoint.startswith(f"repos/{REPO}/pulls"):
            return [self.pr]
        if "/issues/" in endpoint and "/comments" in endpoint:
            return [{"user": {"login": "me"},
                     "body": "attempt 1\n<!-- coordinator-ticket "
                             + json.dumps({"kind": "receipt", "attempt": 1,
                                           "requestId": "ticket:o/r#9:a1"})
                             + " -->"}]
        if endpoint.startswith(f"repos/{REPO}/commits/"):
            return []
        raise AssertionError(f"unexpected endpoint {endpoint}")

    def run_gatekeep(self, payload):
        with open(os.path.join(QUEUE_DIR, "queue.json"), "w") as f:
            json.dump({"next": 2, "items": [],
                       "gatedHeads": {self.key: {"id": 1, "retries": 0, "reviewer": API_REVIEWER,
                                                "at": None, "givenUp": False}}}, f)
        coordq.call = lambda tool, args, rules=None: (0, json.dumps(payload))
        out = io.StringIO()
        with redirect_stdout(out):
            coordq.cmd_gatekeep(argparse.Namespace(config=self.config, dry_run=False))
        return out.getvalue()

    def read_queue(self):
        with open(os.path.join(QUEUE_DIR, "queue.json")) as f:
            return json.load(f)


class RecordedFailureTests(FallbackBase):
    """The recorded no-credits failure of the OpenAI API reviewer."""

    def test_the_recorded_failure_falls_back_to_the_next_reviewer(self):
        queue = {}
        selection = coordq.failed_gate_reviewer(queue, self.key, API_REVIEWER, RECORDED)
        self.assertEqual(selection, CODEX_REVIEWER)

    def test_the_recorded_failure_blocks_that_reviewer_for_every_head(self):
        coordq.failed_gate_reviewer({}, self.key, API_REVIEWER, RECORDED)
        self.assertIn(gate_reviewers.identity(API_REVIEWER), gate_reviewers.blocked_identities())
        # A new gate starts on the next reviewer, not on the blocked one.
        self.assertEqual(coordq.reviewer_model([]), CODEX_REVIEWER)

    def test_a_head_moves_down_the_chain_once_per_reviewer(self):
        queue = {}
        first = coordq.failed_gate_reviewer(queue, self.key, API_REVIEWER, RECORDED)
        self.assertEqual(first, CODEX_REVIEWER)
        second = coordq.failed_gate_reviewer(queue, self.key, first, RECORDED)
        self.assertIsNone(second)

    def test_a_run_with_a_verdict_is_never_retried(self):
        payload = json.loads(json.dumps(RECORDED))
        payload["thread"]["status"] = "completed"
        payload["items"].append({"type": "assistant_message",
                                 "text": "CHECK: PASS " + HEAD + "\nVERDICT: PASS"})
        self.assertIsNone(gate_reviewers.provider_block_reason(payload))
        self.run_gatekeep(payload)
        self.assertEqual(self.read_queue()["items"], [])

    def test_a_gate_without_a_verdict_is_retried_on_the_next_reviewer(self):
        self.run_gatekeep(RECORDED)
        items = [i for i in self.read_queue()["items"] if i["tool"] == "t3_thread_launch"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["args"]["modelSelection"], CODEX_REVIEWER)

    def test_no_gate_is_queued_when_every_reviewer_is_blocked(self):
        gate_reviewers.block_reviewer(API_REVIEWER, "no credits")
        gate_reviewers.block_reviewer(CODEX_REVIEWER, "no credits")
        self.run_gatekeep(RECORDED)
        items = [i for i in self.read_queue()["items"] if i["tool"] == "t3_thread_launch"]
        self.assertEqual(items, [])


class ProbeRecoveryTests(unittest.TestCase):
    """A failed health probe must not hold a reviewer blocked for ever."""

    def setUp(self):
        self.saved = {name: getattr(coordq, name)
                      for name in ("load_receipts", "call")}
        self.addCleanup(lambda: [setattr(coordq, name, value)
                                  for name, value in self.saved.items()])
        self.saved_dir = os.environ.get("COORDQ_DIR")
        os.environ["COORDQ_DIR"] = tempfile.mkdtemp(prefix="coordq-probe-recovery-")
        self.addCleanup(lambda: os.environ.__setitem__("COORDQ_DIR", self.saved_dir)
                        if self.saved_dir is not None
                        else os.environ.pop("COORDQ_DIR", None))
        gate_reviewers.save_blocked({})
        coordq.load_receipts = lambda: {"probe:api:1": "probe-thread"}
        coordq.call = lambda tool, args, rules=None: (
            0, json.dumps({"thread": {"status": "failed", "latestRunId": "r1"},
                            "recentRuns": [{"runId": "r1", "status": "failed",
                                            "error": {"code": "insufficient_quota",
                                                      "message": "You have no credits remaining"}}],
                            "items": []}))

    def test_a_failed_probe_does_not_move_the_deadline_on_a_later_tick(self):
        now = time.time()
        gate_reviewers.block_reviewer(API_REVIEWER, "no credits", now=now)
        gate_reviewers.note_probe(API_REVIEWER, "probe:api:1", now=now)
        coordq.probe_blocked_reviewers(CONFIG)
        first = gate_reviewers.load_blocked()[gate_reviewers.identity(API_REVIEWER)]
        self.assertIsNotNone(first["probeFailedAt"])
        deadline = first["probeAt"]
        # A second tick reads the same failed probe again. The deadline
        # must stay where the failure put it.
        coordq.probe_blocked_reviewers(CONFIG)
        second = gate_reviewers.load_blocked()[gate_reviewers.identity(API_REVIEWER)]
        self.assertEqual(second["probeAt"], deadline)

    def test_a_failed_probe_is_probed_again_an_hour_later(self):
        now = time.time()
        gate_reviewers.block_reviewer(API_REVIEWER, "no credits", now=now)
        gate_reviewers.note_probe(API_REVIEWER, "probe:api:1", now=now)
        coordq.probe_blocked_reviewers(CONFIG)
        record = gate_reviewers.load_blocked()[gate_reviewers.identity(API_REVIEWER)]
        failed_at = record["probeFailedAt"]
        self.assertGreaterEqual(record["probeAt"], failed_at + 3600)
        self.assertFalse(gate_reviewers.probe_due(API_REVIEWER, now=failed_at + 3599))
        self.assertTrue(gate_reviewers.probe_due(API_REVIEWER, now=failed_at + 3600))


class ProviderErrorTests(unittest.TestCase):
    """The provider reasons that block a reviewer for every head."""
    def test_a_recorded_credit_error_blocks_the_reviewer(self):
        payload = {"thread": {"status": "failed", "latestRunId": "r1", **API_REVIEWER},
                   "recentRuns": [{"runId": "r1", "status": "failed", "executedModel": None,
                                   "error": {"code": "insufficient_quota",
                                             "message": "You have no credits remaining"}}]}
        self.assertIsNotNone(gate_reviewers.provider_block_reason(payload))

    def test_a_usage_limit_error_blocks_the_reviewer(self):
        payload = {"thread": {"status": "failed", "latestRunId": "r1", **API_REVIEWER},
                   "recentRuns": [{"runId": "r1", "status": "failed",
                                   "error": {"code": 429, "message": "usage limit reached"}}]}
        self.assertIsNotNone(gate_reviewers.provider_block_reason(payload))

    def test_an_auth_error_blocks_the_reviewer(self):
        payload = {"thread": {"status": "failed", "latestRunId": "r1", **API_REVIEWER},
                   "recentRuns": [{"runId": "r1", "status": "failed",
                                   "error": {"code": 401, "message": "invalid api key"}}]}
        self.assertIsNotNone(gate_reviewers.provider_block_reason(payload))

    def test_a_review_failure_does_not_block_the_reviewer(self):
        payload = {"thread": {"status": "failed", "latestRunId": "r1", **API_REVIEWER},
                   "recentRuns": [{"runId": "r1", "status": "failed",
                                   "executedModel": "openai/gpt-6.2-astra"}],
                   "items": [{"type": "assistant_message", "text": "the diff is wrong"}]}
        self.assertIsNone(gate_reviewers.provider_block_reason(payload))


class ChainShapeTests(unittest.TestCase):
    """The chain is the two GPT-6.2 Astra reviewers, in order."""

    def test_the_api_credits_come_first_and_the_codex_subscription_second(self):
        self.assertEqual(gate_reviewers.REVIEWER_CHAIN,
                         ({"instanceId": "openai-api", "model": "openai/gpt-6.2-astra"},
                          {"instanceId": "codex", "model": "gpt-6.2-astra"}))

    def test_every_chain_member_is_a_gpt_6_2_astra(self):
        for member in gate_reviewers.REVIEWER_CHAIN:
            with self.subTest(member=member):
                self.assertIn("gpt-6.2-astra", member["model"])


class ChainMovementTests(unittest.TestCase):
    """The movement of a head down the reviewer chain."""

    def test_a_head_moves_from_the_chain_head_to_the_second_reviewer(self):
        self.assertEqual(gate_reviewers.reviewer_after(API_REVIEWER), CODEX_REVIEWER)

    def test_an_unknown_reviewer_is_taken_as_the_chain_head(self):
        self.assertEqual(gate_reviewers.reviewer_after(None), CODEX_REVIEWER)
        self.assertEqual(gate_reviewers.reviewer_after({"instanceId": "x", "model": "y"}),
                         CODEX_REVIEWER)

    def test_the_last_reviewer_has_no_next_one(self):
        self.assertIsNone(gate_reviewers.reviewer_after(CODEX_REVIEWER))

    def test_a_blocked_reviewer_is_skipped(self):
        blocked = {gate_reviewers.identity(CODEX_REVIEWER)}
        self.assertIsNone(gate_reviewers.reviewer_after(API_REVIEWER, blocked))

    def test_a_model_name_finds_its_chain_member(self):
        self.assertEqual(gate_reviewers.selection_for_model("openai/gpt-6.2-astra"), API_REVIEWER)
        self.assertEqual(gate_reviewers.selection_for_model("gpt-6.2-astra"), CODEX_REVIEWER)
        self.assertEqual(gate_reviewers.selection_for_model("subscriptions/gpt-6.2-astra"),
                         CODEX_REVIEWER)
        self.assertIsNone(gate_reviewers.selection_for_model("claude-opus-5-5"))


class GateEndingTests(unittest.TestCase):
    """A gate run that ended without a verdict falls back to the next
    reviewer, whatever ended it."""

    def test_a_run_that_ended_without_a_verdict_is_over(self):
        for status in ("completed", "failed", "interrupted", "cancelled",
                       "rolled_back", "errored", "timed_out"):
            with self.subTest(status=status):
                self.assertTrue(coordq.gate_ended(status))

    def test_a_live_run_is_not_over(self):
        for status in ("running", "queued", "starting", "preparing"):
            with self.subTest(status=status):
                self.assertFalse(coordq.gate_ended(status))

    def test_a_missing_status_is_not_an_ending(self):
        self.assertFalse(coordq.gate_ended(None))
        self.assertFalse(coordq.gate_ended(""))


class NewGateStartTests(unittest.TestCase):
    """A new gate starts on the next reviewer while one is blocked."""

    def setUp(self):
        self.saved = os.environ.get("COORDQ_DIR")
        os.environ["COORDQ_DIR"] = tempfile.mkdtemp(prefix="coordq-new-gate-")
        self.addCleanup(self._restore)
        gate_reviewers.save_blocked({})

    def _restore(self):
        if self.saved is None:
            os.environ.pop("COORDQ_DIR", None)
        else:
            os.environ["COORDQ_DIR"] = self.saved

    def test_a_new_gate_starts_on_the_first_reviewer(self):
        args, refusal = coordq.with_model({"taskType": "review", "message": "review"})
        self.assertIsNone(refusal)
        self.assertEqual(args["modelSelection"], API_REVIEWER)

    def test_a_new_gate_skips_a_blocked_reviewer(self):
        gate_reviewers.block_reviewer(API_REVIEWER, "no credits")
        args, refusal = coordq.with_model({"taskType": "review", "message": "review"})
        self.assertIsNone(refusal)
        self.assertEqual(args["modelSelection"], CODEX_REVIEWER)

    def test_a_gate_waits_when_every_reviewer_is_blocked(self):
        gate_reviewers.block_reviewer(API_REVIEWER, "no credits")
        gate_reviewers.block_reviewer(CODEX_REVIEWER, "no credits")
        args, refusal = coordq.with_model({"taskType": "review", "message": "review"})
        self.assertIsNone(args)
        self.assertIn("blocked", refusal)

    def test_a_health_probe_names_its_reviewer_and_is_allowed(self):
        gate_reviewers.block_reviewer(API_REVIEWER, "no credits")
        gate_reviewers.block_reviewer(CODEX_REVIEWER, "no credits")
        args, refusal = coordq.with_model({"taskType": "review", "message": "probe",
                                           "clientRequestId": "probe:openai-api:1",
                                           "modelSelection": API_REVIEWER})
        self.assertIsNone(refusal)
        self.assertEqual(args["modelSelection"], API_REVIEWER)

    def test_an_ordinary_gate_may_not_name_a_blocked_reviewer(self):
        gate_reviewers.block_reviewer(API_REVIEWER, "no credits")
        args, refusal = coordq.with_model({"taskType": "review", "message": "review",
                                            "modelSelection": API_REVIEWER})
        self.assertIsNone(args)
        self.assertIn("blocked", refusal)

    def test_the_ticket_gate_starts_on_the_next_reviewer(self):
        ticket = load_ticket()
        gate_reviewers.block_reviewer(API_REVIEWER, "no credits")
        self.assertEqual(ticket.gate_reviewer([]), CODEX_REVIEWER)

    def test_the_ticket_gate_waits_when_every_reviewer_is_blocked(self):
        ticket = load_ticket()
        gate_reviewers.block_reviewer(API_REVIEWER, "no credits")
        gate_reviewers.block_reviewer(CODEX_REVIEWER, "no credits")
        self.assertIsNone(ticket.gate_reviewer([]))


class BlockedReviewerTests(unittest.TestCase):
    """A blocked reviewer is probed at most once an hour."""

    def setUp(self):
        self.saved = os.environ.get("COORDQ_DIR")
        os.environ["COORDQ_DIR"] = tempfile.mkdtemp(prefix="coordq-blocked-")
        self.addCleanup(lambda: os.environ.__setitem__("COORDQ_DIR", self.saved)
                        if self.saved is not None else os.environ.pop("COORDQ_DIR", None))

    def test_a_blocked_reviewer_is_probed_at_most_once_an_hour(self):
        gate_reviewers.block_reviewer(API_REVIEWER, "no credits", now=1000)
        self.assertFalse(gate_reviewers.probe_due(API_REVIEWER, now=1000))
        self.assertTrue(gate_reviewers.probe_due(API_REVIEWER, now=1000 + 3600))

    def test_a_block_is_logged_once(self):
        first = gate_reviewers.block_reviewer(API_REVIEWER, "no credits", now=1000)
        second = gate_reviewers.block_reviewer(API_REVIEWER, "no credits", now=1100)
        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_an_unblock_is_logged_once(self):
        gate_reviewers.block_reviewer(API_REVIEWER, "no credits", now=1000)
        self.assertIsNotNone(gate_reviewers.unblock_reviewer(API_REVIEWER))
        self.assertIsNone(gate_reviewers.unblock_reviewer(API_REVIEWER))

    def test_a_reset_time_is_read_from_the_error(self):
        self.assertIsNotNone(gate_reviewers.reset_time("usage limit reached, resets in 30 minutes"))
        self.assertIsNone(gate_reviewers.reset_time("usage limit reached"))

    def test_a_reset_is_probed_at_the_reset_and_not_before(self):
        gate_reviewers.block_reviewer(API_REVIEWER, "no credits", now=1000, reset_at=1060)
        self.assertFalse(gate_reviewers.probe_due(API_REVIEWER, now=1059))
        self.assertTrue(gate_reviewers.probe_due(API_REVIEWER, now=1060))

    def test_a_failed_probe_does_not_probe_again_at_once(self):
        gate_reviewers.block_reviewer(API_REVIEWER, "no credits", now=1000, reset_at=1060)
        gate_reviewers.note_probe(API_REVIEWER, "probe-1", now=1060)
        self.assertFalse(gate_reviewers.probe_due(API_REVIEWER, now=1061))
        self.assertFalse(gate_reviewers.probe_due(API_REVIEWER, now=1060 + 3600 - 1))
        self.assertTrue(gate_reviewers.probe_due(API_REVIEWER, now=1060 + 3600))

    def test_a_probe_consumes_the_reset_it_ran_against(self):
        gate_reviewers.block_reviewer(API_REVIEWER, "no credits", now=1000, reset_at=1060)
        gate_reviewers.note_probe(API_REVIEWER, "probe-1", now=1060)
        record = gate_reviewers.load_blocked()[gate_reviewers.identity(API_REVIEWER)]
        self.assertIsNone(record["resetAt"])
        self.assertEqual(record["probeRequestId"], "probe-1")

    def test_a_failed_probe_is_probed_again_an_hour_after_the_failure(self):
        gate_reviewers.block_reviewer(API_REVIEWER, "no credits", now=1000)
        gate_reviewers.note_probe(API_REVIEWER, "probe-1", now=1060)
        gate_reviewers.note_probe_failure(API_REVIEWER, "no credits", now=1100,
                                          request_id="probe-1")
        self.assertFalse(gate_reviewers.probe_due(API_REVIEWER, now=1100))
        self.assertFalse(gate_reviewers.probe_due(API_REVIEWER, now=1100 + 3600 - 1))
        self.assertTrue(gate_reviewers.probe_due(API_REVIEWER, now=1100 + 3600))

    def test_a_failed_probe_is_recorded_once(self):
        gate_reviewers.block_reviewer(API_REVIEWER, "no credits", now=1000)
        gate_reviewers.note_probe(API_REVIEWER, "probe-1", now=1060)
        gate_reviewers.note_probe_failure(API_REVIEWER, "no credits", now=1100,
                                          request_id="probe-1")
        record = gate_reviewers.load_blocked()[gate_reviewers.identity(API_REVIEWER)]
        self.assertEqual(record["probeAt"], 1100 + 3600)
        # A later tick that reads the same failed probe again must not move
        # the deadline, or the reviewer is never probed again.
        gate_reviewers.note_probe_failure(API_REVIEWER, "no credits", now=1200,
                                          request_id="probe-1")
        again = gate_reviewers.load_blocked()[gate_reviewers.identity(API_REVIEWER)]
        self.assertEqual(again["probeAt"], 1100 + 3600)
        self.assertEqual(again["probeFailedAt"], 1100)

    def test_a_failed_probe_waits_for_the_reset_it_names(self):
        gate_reviewers.block_reviewer(API_REVIEWER, "no credits", now=1000)
        gate_reviewers.note_probe(API_REVIEWER, "probe-1", now=1060)
        gate_reviewers.note_probe_failure(API_REVIEWER, "usage limit, resets in 30 minutes",
                                          now=1100, request_id="probe-1")
        self.assertFalse(gate_reviewers.probe_due(API_REVIEWER, now=1100 + 1799))
        self.assertTrue(gate_reviewers.probe_due(API_REVIEWER, now=1100 + 1800))

    def test_a_failure_of_an_older_probe_does_not_move_the_deadline(self):
        gate_reviewers.block_reviewer(API_REVIEWER, "no credits", now=1000)
        gate_reviewers.note_probe(API_REVIEWER, "probe-1", now=1060)
        gate_reviewers.note_probe(API_REVIEWER, "probe-2", now=4660)
        gate_reviewers.note_probe_failure(API_REVIEWER, "no credits", now=4700,
                                          request_id="probe-1")
        record = gate_reviewers.load_blocked()[gate_reviewers.identity(API_REVIEWER)]
        self.assertEqual(record["probeAt"], 4660 + 3600)

    def test_a_new_probe_clears_the_last_failure(self):
        gate_reviewers.block_reviewer(API_REVIEWER, "no credits", now=1000)
        gate_reviewers.note_probe(API_REVIEWER, "probe-1", now=1060)
        gate_reviewers.note_probe_failure(API_REVIEWER, "no credits", now=1100,
                                          request_id="probe-1")
        gate_reviewers.note_probe(API_REVIEWER, "probe-2", now=4700)
        record = gate_reviewers.load_blocked()[gate_reviewers.identity(API_REVIEWER)]
        self.assertIsNone(record["probeFailedAt"])
        self.assertIsNone(record["probeFailedRequestId"])


if __name__ == "__main__":
    unittest.main()
