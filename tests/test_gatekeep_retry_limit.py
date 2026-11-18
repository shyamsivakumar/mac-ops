"""Tests for the retry limit and backoff of a gate that dies without a verdict.

`coordq` is a script without a .py suffix, so it is loaded by path. The queue
directory is a temporary one, so a proof never touches the live queue.
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
from contextlib import redirect_stderr, redirect_stdout
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REPO = "o/r"
HEAD = "a" * 40
OTHER_HEAD = "b" * 40
CONFIG = {"repos": {REPO: {"key": "T", "projectId": "P"}}}
RECEIPT = {"kind": "receipt", "attempt": 1, "requestId": "req-1"}
COMMENT = {"user": {"login": "me"},
           "body": "attempt 1\n<!-- coordinator-ticket "
                   + json.dumps(RECEIPT)
                   + " -->"}
BUILDER_THREAD = {"providerInstanceId": "minimax", "model": "minimax/MiniMax-M3.1-Flash"}
BUILDER_RUNS = [{"executedModel": "minimax/MiniMax-M3.1-Flash"}]
# The gate died for a reviewer-side reason: no message, so no verdict. The
# thread records the gate model coordq launches, which gatekeep requires before
# it treats a dead gate as retryable; setUpModule checks it against coordq.
ASTRA_GATE = {"providerInstanceId": "codex", "model": "gpt-6.2-astra"}
OPUS_GATE = {"providerInstanceId": "claudeAgent", "model": "claude-opus-5-5"}
DEAD_GATE = {"thread": {"status": "failed", **ASTRA_GATE},
             "items": [{"type": "user_message", "text": "review"}],
             "recentRuns": [{"executedModel": None}]}
DEAD_OPUS_GATE = {"thread": {"status": "failed", **OPUS_GATE},
                 "items": [{"type": "user_message", "text": "review"}],
                 "recentRuns": [{"executedModel": None}]}
# A dead Opus gate whose provider refusal says when it comes back, in a window
# shorter than the head's own five-minute retry backoff.
SHORT_RESET_GATE = {"thread": {"status": "failed", "latestRunId": "run-1", **OPUS_GATE},
                    "items": [{"type": "user_message", "text": "review"}],
                    "recentRuns": [{"runId": "run-1", "status": "failed",
                                     "executedModel": None,
                                     "error": {"code": "rate_limit_exceeded",
                                               "message": "too many requests, your plan "
                                                          "resets in 30 seconds"}}]}

coordq = None
QUEUE_DIR = None
SAVED_COORDQ_DIR = None


def load_coordq():
    path = ROOT / "coordinator" / "bin" / "coordq"
    loader = SourceFileLoader("coordq_retry_limit", str(path))
    spec = importlib.util.spec_from_loader("coordq_retry_limit", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def setUpModule():
    global coordq, QUEUE_DIR, SAVED_COORDQ_DIR
    SAVED_COORDQ_DIR = os.environ.get("COORDQ_DIR")
    QUEUE_DIR = tempfile.mkdtemp(prefix="coordq-retry-limit-")
    os.environ["COORDQ_DIR"] = QUEUE_DIR
    coordq = load_coordq()
    launched = {"instanceId": ASTRA_GATE["providerInstanceId"], "model": ASTRA_GATE["model"]}
    if coordq.ASTRA_MODEL != launched:
        raise AssertionError(f"ASTRA_GATE drifted from coordq.ASTRA_MODEL: {coordq.ASTRA_MODEL}")


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


class RetryLimitBase(unittest.TestCase):
    """One open pull request whose gate died without a verdict."""

    def setUp(self):
        self.saved = {name: getattr(coordq, name)
                      for name in ("gh_json", "load_receipts", "read_builder_thread",
                                   "router_chain", "subprocess", "call", "gate_request")}
        self.addCleanup(lambda: [setattr(coordq, name, value)
                                 for name, value in self.saved.items()])
        self.pr = {"draft": False, "number": 7, "head": {"sha": HEAD},
                   "body": f"Refs #9\nBuilder check: PASS {HEAD}\n"}
        self.key = f"gate:{REPO}#7:{HEAD}"
        coordq.subprocess = types.SimpleNamespace(
            run=lambda *a, **k: FakeRun("me\n"))
        coordq.load_receipts = lambda: {RECEIPT["requestId"]: "builder-1", self.key: "gate-1"}
        coordq.read_builder_thread = lambda thread_id: (BUILDER_THREAD, BUILDER_RUNS)
        coordq.router_chain = lambda route: []
        coordq.gh_json = self.fake_gh
        coordq.call = lambda tool, args, rules=None: (0, json.dumps(DEAD_GATE))
        self.config = os.path.join(QUEUE_DIR, "gatekeep-config.json")
        with open(self.config, "w") as f:
            json.dump(CONFIG, f)
        self.addCleanup(self.clear_blocks)

    def fake_gh(self, endpoint):
        if endpoint.startswith(f"repos/{REPO}/pulls"):
            return [self.pr]
        if "/issues/" in endpoint and "/comments" in endpoint:
            return [COMMENT]
        if endpoint.startswith(f"repos/{REPO}/commits/"):
            return []
        raise AssertionError(f"unexpected endpoint {endpoint}")

    def write_queue(self, heads=None, items=None):
        payload = {"next": 1, "items": items or [],
                   "gatedHeads": heads if heads is not None else {}}
        with open(os.path.join(QUEUE_DIR, "queue.json"), "w") as f:
            json.dump(payload, f)

    def read_queue(self):
        with open(os.path.join(QUEUE_DIR, "queue.json")) as f:
            return json.load(f)

    def gate_items(self):
        return [item for item in self.read_queue()["items"]
                if item["tool"] == "t3_thread_launch"]

    def clear_blocks(self):
        path = os.path.join(QUEUE_DIR, "reviewers-blocked.json")
        if os.path.exists(path):
            os.unlink(path)

    def run_gatekeep(self, dry_run=False):
        args = argparse.Namespace(config=self.config, dry_run=dry_run)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            coordq.cmd_gatekeep(args)
        return out.getvalue(), err.getvalue()


class FirstRetryTest(RetryLimitBase):
    """A gate that died without a verdict still gets its first retry."""

    def test_a_legacy_head_is_retried(self):
        self.write_queue(heads={self.key: 4})
        out, _ = self.run_gatekeep()
        self.assertIn("regating o/r#7: aaaaaaaa (gate died without a verdict)", out)
        self.assertEqual(len(self.gate_items()), 1)
        self.assertEqual(self.read_queue()["gatedHeads"][self.key]["retries"], 1)

    def test_a_head_with_no_retry_yet_is_retried(self):
        self.write_queue(heads={self.key: {"id": 4, "retries": 0, "at": None, "givenUp": False}})
        out, _ = self.run_gatekeep()
        self.assertIn("regating o/r#7", out)
        self.assertEqual(len(self.gate_items()), 1)
        self.assertEqual(self.read_queue()["gatedHeads"][self.key]["retries"], 1)

    def test_a_gate_that_never_ran_is_queued_once(self):
        self.write_queue()
        out, _ = self.run_gatekeep()
        self.assertEqual(len(self.gate_items()), 1)
        self.assertNotIn("regating", out)
        self.assertEqual(self.read_queue()["gatedHeads"][self.key]["retries"], 0)

    def test_a_gate_with_a_verdict_is_not_retried(self):
        coordq.call = lambda tool, args, rules=None: (
            0, json.dumps({"thread": {"status": "completed"},
                           "items": [{"type": "assistant_message", "text": "VERDICT: PASS"}]}))
        self.write_queue(heads={self.key: 4})
        out, _ = self.run_gatekeep()
        self.assertEqual(self.gate_items(), [])
        self.assertNotIn("regating", out)


class NonAstraGateTest(RetryLimitBase):
    """A dead gate that did not run on the Astra model is left alone."""

    def test_a_dead_opus_gate_is_not_requeued(self):
        coordq.call = lambda tool, args, rules=None: (0, json.dumps(DEAD_OPUS_GATE))
        self.write_queue(heads={self.key: 4})
        out, _ = self.run_gatekeep()
        self.assertNotIn("regating", out)
        self.assertEqual(self.gate_items(), [])
        # The head record is a dict now: the dead Opus gate is not requeued
        # and the head is recorded as given up. The launch reviewer is kept
        # beside it, so a later read of this head knows which reviewer ran.
        self.assertEqual(self.read_queue()["gatedHeads"][self.key],
                         {"id": 4, "retries": 0, "at": None, "givenUp": True,
                          "reviewer": None})


class BackoffTest(RetryLimitBase):
    """The second retry waits, so a reviewer that cannot run is not
    relaunched on every run."""

    def test_a_second_retry_waits_for_the_backoff(self):
        self.write_queue(heads={self.key: {"id": 4, "retries": 1,
                                          "at": time.time(), "givenUp": False}})
        out, _ = self.run_gatekeep()
        self.assertEqual(self.gate_items(), [])
        self.assertNotIn("regating", out)

    def test_a_blocking_failure_in_the_backoff_still_blocks_the_reviewer(self):
        # The head still has retry budget, so the backoff holds it. The block
        # is recorded anyway, or the next head starts on the reviewer that just
        # refused for want of credits.
        coordq.call = lambda tool, args, rules=None: (0, json.dumps(
            {"thread": {"status": "failed", **OPUS_GATE, "latestRunId": "run-1"},
             "items": [{"type": "user_message", "text": "review"}],
             "recentRuns": [{"runId": "run-1", "status": "failed", "executedModel": None,
                              "error": {"code": "insufficient_quota",
                                        "message": "no credits remaining"}}]}))
        self.write_queue(heads={self.key: {"id": 4, "retries": 1,
                                          "at": time.time(), "givenUp": False,
                                          "reviewer": OPUS_GATE}})
        out, _ = self.run_gatekeep()
        self.assertNotIn("regating", out)
        self.assertEqual(self.gate_items(), [])
        self.assertTrue(coordq.is_blocked(reviewer_of(OPUS_GATE)))
        self.assertEqual(coordq.reviewer_model([]), reviewer_of(ASTRA_GATE))

    def test_a_repeated_read_does_not_extend_the_block(self):
        # Every gatekeep pass reads the same dead gate. The first pass records
        # the block; a later pass must leave its window where it is.
        coordq.call = lambda tool, args, rules=None: (0, json.dumps(
            {"thread": {"status": "failed", **OPUS_GATE, "latestRunId": "run-1"},
             "items": [{"type": "user_message", "text": "review"}],
             "recentRuns": [{"runId": "run-1", "status": "failed", "executedModel": None,
                              "error": {"code": "insufficient_quota",
                                        "message": "your plan resets in 20 minutes"}}]}))
        self.write_queue(heads={self.key: {"id": 4, "retries": 1,
                                          "at": time.time(), "givenUp": False,
                                          "reviewer": OPUS_GATE}})
        self.run_gatekeep()
        first = self.blocked_until()
        self.assertIsNotNone(first)
        time.sleep(0.01)
        self.run_gatekeep()
        self.assertEqual(self.blocked_until(), first)

    def test_a_short_reset_is_not_blocked_again_after_it_ends(self):
        # The provider says it comes back in 30 seconds, so its block ends
        # inside this head's five-minute backoff. The next pass reads the same
        # dead run and must leave the freed reviewer to other heads instead of
        # blocking it a second time for one failure.
        coordq.call = lambda tool, args, rules=None: (0, json.dumps(SHORT_RESET_GATE))
        self.write_queue(heads={self.key: {"id": 4, "retries": 1,
                                          "at": time.time(), "givenUp": False,
                                          "reviewer": OPUS_GATE}})
        before = len(self.block_lines())
        self.run_gatekeep()
        self.assertAlmostEqual(self.blocked_until() - time.time(), 30, delta=5)
        self.assertEqual(len(self.block_lines()), before + 1)
        self.end_blocks()
        self.run_gatekeep()
        self.assertFalse(coordq.is_blocked(reviewer_of(OPUS_GATE)))
        self.assertEqual(len(self.block_lines()), before + 1)
        self.assertEqual(self.gate_items(), [])

    def test_a_new_failure_after_a_short_reset_still_blocks(self):
        # The failure is blocked once, not never: a run the block was not
        # recorded for still blocks the reviewer.
        coordq.call = lambda tool, args, rules=None: (0, json.dumps(SHORT_RESET_GATE))
        self.write_queue(heads={self.key: {"id": 4, "retries": 1,
                                          "at": time.time(), "givenUp": False,
                                          "reviewer": OPUS_GATE}})
        before = len(self.block_lines())
        self.run_gatekeep()
        self.end_blocks()
        newer = json.loads(json.dumps(SHORT_RESET_GATE))
        newer["thread"]["latestRunId"] = "run-2"
        newer["recentRuns"][0]["runId"] = "run-2"
        coordq.call = lambda tool, args, rules=None: (0, json.dumps(newer))
        self.run_gatekeep()
        self.assertTrue(coordq.is_blocked(reviewer_of(OPUS_GATE)))
        self.assertEqual(len(self.block_lines()), before + 2)

    def end_blocks(self):
        """Put every recorded block in the past, as its provider window ending does."""
        with open(os.path.join(QUEUE_DIR, "reviewers-blocked.json")) as f:
            records = json.load(f)
        for record in records.values():
            record["until"] = time.time() - 1
        with open(os.path.join(QUEUE_DIR, "reviewers-blocked.json"), "w") as f:
            json.dump(records, f)

    def block_lines(self):
        try:
            with open(os.path.join(QUEUE_DIR, "dispatch.log")) as f:
                return [line for line in f if "blocked until" in line]
        except OSError:
            return []

    def blocked_until(self):
        try:
            with open(os.path.join(QUEUE_DIR, "reviewers-blocked.json")) as f:
                records = json.load(f)
        except OSError:
            return None
        return records.get(f"{OPUS_GATE['providerInstanceId']}:{OPUS_GATE['model']}", {}).get("until")

    def test_a_second_retry_happens_after_the_backoff(self):
        self.write_queue(heads={self.key: {"id": 4, "retries": 1,
                                          "at": time.time() - coordq.GATE_RETRY_BACKOFF - 1,
                                          "givenUp": False}})
        out, _ = self.run_gatekeep()
        self.assertIn("regating o/r#7", out)
        self.assertEqual(len(self.gate_items()), 1)
        self.assertEqual(self.read_queue()["gatedHeads"][self.key]["retries"], 2)


class GiveUpTest(RetryLimitBase):
    """A head retried to the limit is given up once and left alone."""

    def setUp(self):
        super().setUp()
        self.write_queue(heads={self.key: {"id": 4, "retries": coordq.GATE_RETRY_LIMIT,
                                          "at": time.time(), "givenUp": False}})

    def test_the_dry_run_prints_one_give_up_line_and_no_queue_line(self):
        before = self.read_queue()
        out, _ = self.run_gatekeep(dry_run=True)
        self.assertNotIn("would queue gate:", out)
        lines = [line for line in out.splitlines() if line.startswith("gave up ")]
        self.assertEqual(len(lines), 1)
        self.assertIn(self.key, lines[0])
        self.assertIn(f"after {coordq.GATE_RETRY_LIMIT} retries without a verdict", lines[0])
        self.assertEqual(self.read_queue(), before)

    def test_an_odd_record_does_not_stop_the_run(self):
        self.write_queue(heads={self.key: {"id": 4, "retries": "x", "at": "yesterday",
                                          "givenUp": False}})
        out, _ = self.run_gatekeep(dry_run=True)
        self.assertIn("would queue " + self.key, out)

    def test_the_give_up_is_written_and_announced_once(self):
        out, _ = self.run_gatekeep()
        self.assertEqual(len([line for line in out.splitlines() if line.startswith("gave up ")]), 1)
        self.assertEqual(self.gate_items(), [])
        self.assertTrue(self.read_queue()["gatedHeads"][self.key]["givenUp"])
        again, _ = self.run_gatekeep()
        self.assertNotIn("gave up", again)
        self.assertEqual(self.gate_items(), [])

    def test_a_changed_head_is_retried_again(self):
        self.run_gatekeep()
        self.pr["head"]["sha"] = OTHER_HEAD
        self.pr["body"] = f"Refs #9\nBuilder check: PASS {OTHER_HEAD}\n"
        out, _ = self.run_gatekeep()
        changed = f"gate:{REPO}#7:{OTHER_HEAD}"
        self.assertIn("queued " + changed, out)
        heads = self.read_queue()["gatedHeads"]
        self.assertTrue(heads[self.key]["givenUp"])
        self.assertEqual(heads[changed]["retries"], 0)


class ExplicitGateTest(RetryLimitBase):
    """An operator asking for a gate explicitly still gets it."""

    def setUp(self):
        super().setUp()
        self.write_queue(heads={self.key: {"id": 4, "retries": coordq.GATE_RETRY_LIMIT,
                                          "at": time.time(), "givenUp": True}})
        self.gate = {"projectId": "P", "title": "T-9 review #7 aaaaaaaa",
                     "modelSelection": {"instanceId": "claudeAgent", "model": "claude-opus-5-5"},
                     "runtimeMode": "full-access", "workspaceStrategy": {"type": "root"},
                     "clientRequestId": self.key, "message": "review"}
        # The gate request carries the builder's executed models, so the
        # reviewer route follows the builder's real vendor.
        coordq.gate_request = lambda *a, **k: (
            self.key, self.gate, coordq.builder_models(BUILDER_THREAD, BUILDER_RUNS))
        self.pull = {"state": "open", "draft": False, "number": 7, "head": {"sha": HEAD},
                     "body": "Refs #9"}

        def fake_run(command, **kwargs):
            if command[:2] == ["gh", "api"] and command[2] == "user":
                return FakeRun("me\n")
            return FakeRun(json.dumps(self.pull))

        coordq.subprocess = types.SimpleNamespace(run=fake_run)

    def gate_once(self):
        args = argparse.Namespace(ref=f"{REPO}#7", config=self.config)
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            coordq.cmd_gate(args)
        return out.getvalue()

    def test_a_given_up_head_is_queued(self):
        out = self.gate_once()
        self.assertIn("queued " + self.key, out)
        self.assertEqual(len(self.gate_items()), 1)
        # The retry budget is not reopened, because the reviewer has not changed.
        self.assertEqual(self.read_queue()["gatedHeads"][self.key]["retries"],
                         coordq.GATE_RETRY_LIMIT)
        self.assertEqual(self.gate_items()[0]["args"]["clientRequestId"], self.key)

    def test_a_second_explicit_gate_is_refused(self):
        self.gate_once()
        with self.assertRaises(SystemExit):
            with redirect_stderr(io.StringIO()):
                self.gate_once()
        self.assertEqual(len(self.gate_items()), 1)

    def test_a_given_up_head_that_dies_again_is_given_up_in_one_line(self):
        self.gate_once()
        out, _ = self.run_gatekeep()
        self.assertEqual(len([line for line in out.splitlines()
                              if line.startswith("gave up ")]), 1)
        self.assertEqual(len(self.gate_items()), 1)
        self.assertTrue(self.read_queue()["gatedHeads"][self.key]["givenUp"])

    def test_a_live_head_is_still_refused(self):
        self.write_queue(heads={self.key: {"id": 4, "retries": 1,
                                          "at": time.time(), "givenUp": False}})
        with self.assertRaises(SystemExit):
            with redirect_stderr(io.StringIO()):
                self.gate_once()
        self.assertEqual(self.gate_items(), [])

    def test_every_reviewer_blocked_refuses_an_explicit_gate(self):
        now = time.time()
        with open(os.path.join(QUEUE_DIR, "reviewers-blocked.json"), "w") as f:
            json.dump({f"{entry['instanceId']}:{entry['model']}": {"until": now + 600, "at": now}
                       for entry in coordq.REVIEWER_CHAIN}, f)
        args = argparse.Namespace(ref=f"{REPO}#7", config=self.config)
        err = io.StringIO()
        with self.assertRaises(SystemExit):
            with redirect_stderr(err):
                coordq.cmd_gate(args)
        self.assertIn("every gate reviewer is blocked", err.getvalue())
        self.assertEqual(self.gate_items(), [])

    def test_a_reviewer_blocked_after_it_was_chosen_is_refused(self):
        # The model is chosen before the queue lock, so another gatekeep run
        # can block it in between. The chosen reviewer is refused instead of
        # queued.
        chosen = coordq.gate_request

        def blocked_meanwhile(*a, **k):
            now = time.time()
            with open(os.path.join(QUEUE_DIR, "reviewers-blocked.json"), "w") as f:
                json.dump({f"{entry['instanceId']}:{entry['model']}":
                           {"until": now + 600, "at": now}
                           for entry in coordq.REVIEWER_CHAIN}, f)
            return chosen(*a, **k)

        coordq.gate_request = blocked_meanwhile
        args = argparse.Namespace(ref=f"{REPO}#7", config=self.config)
        err = io.StringIO()
        with self.assertRaises(SystemExit):
            with redirect_stderr(err):
                coordq.cmd_gate(args)
        self.assertIn("every gate reviewer is blocked", err.getvalue())
        self.assertEqual(self.gate_items(), [])

    def test_a_chosen_reviewer_blocked_alone_names_that_reviewer(self):
        coordq.block_reviewer(coordq.REVIEWER_CHAIN[-1],
                              {"error": {"code": "insufficient_quota",
                                         "message": "no credits remaining"}})
        args = argparse.Namespace(ref=f"{REPO}#7", config=self.config)
        err = io.StringIO()
        with self.assertRaises(SystemExit):
            with redirect_stderr(err):
                coordq.cmd_gate(args)
        self.assertIn("gate reviewer claudeAgent:claude-opus-5-5 is blocked",
                      err.getvalue())
        self.assertEqual(self.gate_items(), [])


def reviewer_of(thread):
    """The chain-shaped selection of a reviewer a gate thread ran on."""
    return {"instanceId": thread["providerInstanceId"], "model": thread["model"]}


# A dead Opus gate whose failure is the provider refusing to run: the run the
# thread names is the failed one, and it names the refusal.
QUOTA_FAILURE = {"thread": {"status": "failed", "latestRunId": "run-1", **OPUS_GATE},
                 "items": [{"type": "user_message", "text": "review"}],
                 "recentRuns": [{"runId": "run-1", "status": "failed", "executedModel": None,
                                 "error": {"code": "insufficient_quota",
                                           "message": "no credits remaining"}}]}


class RetryLimitBlocksReviewerTest(RetryLimitBase):
    """A reviewer that ran out of credits is blocked before the head is
    given up, so the next head cannot start on it."""

    def setUp(self):
        super().setUp()
        saved_limit = coordq.GATE_RETRY_LIMIT
        self.addCleanup(setattr, coordq, "GATE_RETRY_LIMIT", saved_limit)
        coordq.GATE_RETRY_LIMIT = 1
        self.clear_blocks()

    def test_the_reviewer_out_of_credits_is_blocked_when_the_head_gives_up(self):
        refusal = {"error": {"code": "insufficient_quota",
                            "message": "no credits remaining"}}
        coordq.block_reviewer(reviewer_of(ASTRA_GATE), refusal)
        coordq.call = lambda tool, args, rules=None: (0, json.dumps(QUOTA_FAILURE))
        self.write_queue(heads={self.key: {"id": 4, "retries": 1, "at": time.time(),
                                           "givenUp": False, "reviewer": OPUS_GATE}})
        out, _ = self.run_gatekeep()
        self.assertIn("gave up " + self.key, out)
        self.assertTrue(self.read_queue()["gatedHeads"][self.key]["givenUp"])
        self.assertTrue(coordq.is_blocked(reviewer_of(OPUS_GATE)))
        # Both reviewers are out of credits, so the next head waits instead
        # of starting on the Opus block the give-up just recorded.
        self.pr["head"]["sha"] = OTHER_HEAD
        self.pr["body"] = f"Refs #9\nBuilder check: PASS {OTHER_HEAD}\n"
        out, _ = self.run_gatekeep()
        self.assertIn("defer " + f"{REPO}#7: every gate reviewer is blocked", out)
        self.assertEqual(self.gate_items(), [])


if __name__ == "__main__":
    unittest.main()
