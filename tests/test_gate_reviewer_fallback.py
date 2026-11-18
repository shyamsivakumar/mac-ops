"""Replay tests for a gate that ends without a verdict, and for the reviewer
a blocking provider error holds.

`coordq` is a script without a .py suffix, so it is loaded by path. The queue
directory is a temporary one, so a proof never touches the live queue.
"""
import argparse
import importlib.util
import io
import json
import os
import sys
import tempfile
import time
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "gate"

REPO = "o/r"
HEAD = "a" * 40
NEXT_HEAD = "b" * 40
CONFIG = {"repos": {REPO: {"key": "T", "projectId": "P"}}}
RECEIPT = {"kind": "receipt", "attempt": 1, "requestId": "req-1"}
COMMENT = {"user": {"login": "me"},
           "body": "attempt 1\n<!-- coordinator-ticket "
                   + json.dumps(RECEIPT)
                   + " -->"}
BUILDER_THREAD = {"providerInstanceId": "minimax", "model": "minimax/MiniMax-M3.1-Flash"}
BUILDER_RUNS = [{"executedModel": "minimax/MiniMax-M3.1-Flash"}]
# A gate that failed before any model answered: no message, so no verdict.
DEAD_GATE = {"thread": {"status": "failed", "providerInstanceId": "codex",
                        "model": "gpt-6.2-astra"},
             "items": [{"type": "user_message", "text": "review"}],
             "recentRuns": [{"executedModel": None}]}
# A gate that died before a model ran records neither a provider nor a model.
MODELLESS_GATE = {"thread": {"status": "failed"},
                  "items": [{"type": "user_message", "text": "review"}],
                  "recentRuns": []}
# The same, launched on a reviewer that then refused for want of credits.
MODELLESS_NO_CREDITS = {"thread": {"status": "failed",
                                   "error": {"code": "usage_limit",
                                             "message": "You have no credits left"}},
                        "items": [{"type": "user_message", "text": "review"}],
                        "recentRuns": []}
DEAD_OPUS_GATE = {"thread": {"status": "failed", "providerInstanceId": "claudeAgent",
                             "model": "claude-opus-5-5"},
                  "items": [{"type": "user_message", "text": "review"}],
                  "recentRuns": []}
VERDICT_GATE = {"thread": {"status": "completed"},
                "items": [{"type": "assistant_message",
                           "text": f"CHECK: PASS {HEAD}\nVERDICT: PASS"}]}
NO_CREDITS = "You have no credits left on this plan; it resets in 30 minutes."


def recorded_no_credits():
    """The recorded gate run of 2026-11-17 whose provider ran out of credits."""
    with open(FIXTURES / "codex-astra-no-credits.json") as f:
        return json.load(f)


def utc_text(seconds_from_now):
    """A recorded time the provider would write, that many seconds from now."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ",
                        time.gmtime(time.time() + seconds_from_now))


def gate_failed_ago(seconds_ago, message=NO_CREDITS, run_id="run-late-1"):
    """A gate whose run failed `seconds_ago`, read for the first time now."""
    error = {"code": "usage_limit", "message": message}
    return {"thread": {"threadId": "gate-late", "status": "failed",
                       "providerInstanceId": "codex", "model": "gpt-6.2-astra",
                       "latestRunId": run_id, "error": error,
                       "updatedAt": utc_text(0)},
            "items": [{"type": "user_message", "text": "review"}],
            "recentRuns": [{"runId": run_id, "status": "failed",
                             "executedModel": "gpt-6.2-astra",
                             "startedAt": utc_text(-seconds_ago - 120),
                             "completedAt": utc_text(-seconds_ago),
                             "error": error}]}


coordq = None
gate_reviewers = None
QUEUE_DIR = None
SAVED_COORDQ_DIR = None
CHAIN_HEAD = NEXT_REVIEWER = None


def load_coordq():
    path = ROOT / "coordinator" / "bin" / "coordq"
    loader = SourceFileLoader("coordq_fallback", str(path))
    spec = importlib.util.spec_from_loader("coordq_fallback", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def setUpModule():
    global coordq, gate_reviewers, QUEUE_DIR, SAVED_COORDQ_DIR, CHAIN_HEAD, NEXT_REVIEWER
    SAVED_COORDQ_DIR = os.environ.get("COORDQ_DIR")
    QUEUE_DIR = tempfile.mkdtemp(prefix="coordq-fallback-")
    os.environ["COORDQ_DIR"] = QUEUE_DIR
    coordq = load_coordq()
    gate_reviewers = sys.modules["gate_reviewers"]
    CHAIN_HEAD, NEXT_REVIEWER = coordq.REVIEWER_CHAIN


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


class ReplayBase(unittest.TestCase):
    """One open pull request, its builder, and the gate run replayed for it."""

    gate = DEAD_GATE

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="coordq-fallback-case-", dir=QUEUE_DIR)
        self.saved = {name: getattr(coordq, name)
                      for name in ("gh_json", "load_receipts", "read_builder_thread",
                                   "router_chain", "subprocess", "call")}
        self.saved_dir = coordq.DIR
        self.addCleanup(self.restore)
        os.environ["COORDQ_DIR"] = self.dir
        coordq.DIR = self.dir
        self.pr = {"draft": False, "number": 7, "head": {"sha": HEAD},
                   "body": f"Refs #9\nBuilder check: PASS {HEAD}\n"}
        self.key = f"gate:{REPO}#7:{HEAD}"
        coordq.subprocess = types.SimpleNamespace(run=lambda *a, **k: FakeRun("me\n"))
        coordq.load_receipts = lambda: {RECEIPT["requestId"]: "builder-1", self.key: "gate-1"}
        coordq.read_builder_thread = lambda thread_id: (BUILDER_THREAD, BUILDER_RUNS)
        coordq.router_chain = lambda route: []
        coordq.gh_json = self.fake_gh
        coordq.call = lambda tool, args, rules=None: (0, json.dumps(self.gate))
        self.config = os.path.join(self.dir, "gatekeep-config.json")
        with open(self.config, "w") as f:
            json.dump(CONFIG, f)

    def restore(self):
        for name, value in self.saved.items():
            setattr(coordq, name, value)
        coordq.DIR = self.saved_dir
        os.environ["COORDQ_DIR"] = QUEUE_DIR

    def fake_gh(self, endpoint):
        if endpoint.startswith(f"repos/{REPO}/pulls"):
            return [self.pr]
        if "/issues/" in endpoint and "/comments" in endpoint:
            return [COMMENT]
        if endpoint.startswith(f"repos/{REPO}/commits/"):
            return []
        raise AssertionError(f"unexpected endpoint {endpoint}")

    def next_head(self):
        self.pr["head"]["sha"] = NEXT_HEAD
        self.pr["body"] = f"Refs #9\nBuilder check: PASS {NEXT_HEAD}\n"

    def write_queue(self, heads=None, items=None, tried=None):
        payload = {"next": 1, "items": items or [],
                   "gatedHeads": heads if heads is not None else {},
                   "gateReviewers": tried or {}}
        with open(os.path.join(self.dir, "queue.json"), "w") as f:
            json.dump(payload, f)

    def read_queue(self):
        with open(os.path.join(self.dir, "queue.json")) as f:
            return json.load(f)

    def gate_items(self):
        return [item for item in self.read_queue()["items"]
                if item["tool"] == "t3_thread_launch"]

    def run_gatekeep(self, dry_run=False):
        args = argparse.Namespace(config=self.config, dry_run=dry_run)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            coordq.cmd_gatekeep(args)
        return out.getvalue(), err.getvalue()

    def blocked_records(self):
        try:
            with open(os.path.join(self.dir, "reviewers-blocked.json")) as f:
                return json.load(f)
        except OSError:
            return {}

    def write_blocked(self, records):
        with open(os.path.join(self.dir, "reviewers-blocked.json"), "w") as f:
            json.dump(records, f)

    def log_lines(self):
        try:
            with open(os.path.join(self.dir, "dispatch.log")) as f:
                return f.read().splitlines()
        except OSError:
            return []


def identity(selection):
    return f"{selection['instanceId']}:{selection['model']}"


class NoVerdictFallbackTest(ReplayBase):
    """A gate that ends without a verdict is retried once, one reviewer down."""

    def test_a_no_verdict_run_moves_to_the_next_reviewer(self):
        self.write_queue(heads={self.key: {"id": 4, "retries": 0, "at": None, "givenUp": False}})
        out, _ = self.run_gatekeep()
        self.assertIn("regating o/r#7: aaaaaaaa (gate died without a verdict)", out)
        items = self.gate_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["args"]["modelSelection"], NEXT_REVIEWER)
        self.assertEqual(self.read_queue()["gatedHeads"][self.key]["retries"], 1)

    def test_a_dead_run_that_records_no_model_moves_down_too(self):
        self.gate = MODELLESS_GATE
        self.write_queue(heads={self.key: {"id": 4, "retries": 0, "at": None, "givenUp": False}})
        out, _ = self.run_gatekeep()
        self.assertIn("regating o/r#7", out)
        items = self.gate_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["args"]["modelSelection"], NEXT_REVIEWER)

    def test_a_verdict_run_is_not_retried(self):
        self.gate = VERDICT_GATE
        self.write_queue(heads={self.key: 4})
        out, _ = self.run_gatekeep()
        self.assertEqual(self.gate_items(), [])
        self.assertNotIn("regating", out)

    def test_the_last_reviewer_is_not_retried_on_itself(self):
        self.gate = DEAD_OPUS_GATE
        self.write_queue(heads={self.key: {"id": 4, "retries": 1, "at": 0, "givenUp": False}})
        self.run_gatekeep()
        self.assertEqual(self.gate_items(), [])
        self.assertTrue(self.read_queue()["gatedHeads"][self.key]["givenUp"])

    def test_one_move_down_per_head(self):
        # This head already moved to the second reviewer once, so it is not
        # moved again and not re-queued on the reviewer it came from.
        self.write_queue(heads={self.key: {"id": 5, "retries": 1, "at": 0, "givenUp": False}},
                         tried={self.key: [identity(NEXT_REVIEWER)]})
        out, _ = self.run_gatekeep()
        self.assertNotIn("regating", out)
        self.assertEqual(self.gate_items(), [])
        self.assertTrue(self.read_queue()["gatedHeads"][self.key]["givenUp"])


class BlockedReviewerTest(ReplayBase):
    """A blocking provider error holds that reviewer for every head."""

    def setUp(self):
        super().setUp()
        self.gate = recorded_no_credits()

    def test_a_no_credits_error_blocks_that_reviewer_for_its_window(self):
        self.write_queue(heads={self.key: 4})
        self.run_gatekeep()
        records = self.blocked_records()
        self.assertEqual(list(records), [identity(CHAIN_HEAD)])
        # The recorded error says the plan resets in 30 minutes.
        self.assertAlmostEqual(records[identity(CHAIN_HEAD)]["until"] - time.time(),
                              1800, delta=60)
        lines = [line for line in self.log_lines() if "blocked until" in line]
        self.assertEqual(len(lines), 1)
        self.assertIn(identity(CHAIN_HEAD), lines[0])

    def test_the_block_lifts_after_the_window(self):
        self.write_blocked({identity(CHAIN_HEAD): {"until": time.time() - 1,
                                                   "at": time.time() - 3601}})
        self.write_queue()
        self.run_gatekeep()
        self.assertEqual(self.blocked_records(), {})
        lines = [line for line in self.log_lines() if "unblocked" in line]
        self.assertEqual(len(lines), 1)
        self.assertIn(identity(CHAIN_HEAD), lines[0])
        self.assertEqual(coordq.reviewer_model([]), CHAIN_HEAD)

    def test_a_new_gate_starts_on_the_next_reviewer_while_blocked(self):
        self.write_blocked({identity(CHAIN_HEAD): {"until": time.time() + 600,
                                                   "at": time.time()}})
        self.assertEqual(coordq.reviewer_model([]), NEXT_REVIEWER)
        self.assertEqual(coordq.backstop_model({}, []), NEXT_REVIEWER)
        self.next_head()
        out, _ = self.run_gatekeep()
        items = self.gate_items()
        self.assertEqual(len(items), 1)
        self.assertIn(f"reviewer {NEXT_REVIEWER['instanceId']}", out)
        self.assertEqual(items[0]["args"]["modelSelection"], NEXT_REVIEWER)

    def test_every_reviewer_blocked_defers_the_head(self):
        now = time.time()
        self.write_blocked({identity(entry): {"until": now + 600, "at": now}
                            for entry in coordq.REVIEWER_CHAIN})
        self.next_head()
        out, _ = self.run_gatekeep()
        self.assertIn("defer o/r#7: every gate reviewer is blocked", out)
        self.assertEqual(self.gate_items(), [])
        self.assertEqual(coordq.reviewer_model([]), CHAIN_HEAD)

    def test_one_block_line_per_block(self):
        queue = {"next": 1, "items": [], "gatedHeads": {}, "gateReviewers": {}}
        first = coordq.failed_gate_reviewer(queue, self.key, CHAIN_HEAD, self.gate)
        second = coordq.failed_gate_reviewer(queue, self.key, CHAIN_HEAD, self.gate)
        self.assertEqual(first, NEXT_REVIEWER)
        self.assertIsNone(second)
        lines = [line for line in self.log_lines() if "blocked until" in line]
        self.assertEqual(len(lines), 1)
        self.assertEqual(len([line for line in self.log_lines() if "unblocked" in line]), 0)

    def test_a_dry_run_blocks_nobody(self):
        self.write_queue(heads={self.key: 4})
        self.run_gatekeep(dry_run=True)
        self.assertEqual(self.blocked_records(), {})
        self.assertEqual([line for line in self.log_lines() if "blocked" in line], [])

    def test_a_run_that_answered_does_not_block(self):
        answered = {"thread": {"status": "completed", "error": {"message": "no credits"}},
                    "items": [{"type": "assistant_message", "text": "VERDICT: FAIL"}]}
        self.assertIsNone(gate_reviewers.blocking_until(answered))

    def test_a_mode_less_run_is_attributed_to_the_reviewer_it_launched_on(self):
        # Astra was blocked, so this head started on Opus and died before
        # recording a model. The launch record says which reviewer it ran on.
        self.gate = MODELLESS_NO_CREDITS
        self.write_queue(heads={self.key: {"id": 4, "retries": 0, "at": None,
                                           "givenUp": False, "reviewer": NEXT_REVIEWER}})
        out, _ = self.run_gatekeep()
        self.assertEqual(list(self.blocked_records()), [identity(NEXT_REVIEWER)])
        # Nothing is left below Opus, so the head waits instead of being
        # queued on the reviewer that just refused.
        self.assertEqual(self.gate_items(), [])
        self.assertTrue(self.read_queue()["gatedHeads"][self.key]["givenUp"])
        self.assertNotIn("regating", out)

    def test_the_queue_records_the_reviewer_a_gate_launches_on(self):
        self.write_blocked({identity(CHAIN_HEAD): {"until": time.time() + 600,
                                                   "at": time.time()}})
        self.next_head()
        self.run_gatekeep()
        items = self.gate_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(self.read_queue()["gatedHeads"][f"gate:{REPO}#7:{NEXT_HEAD}"]["reviewer"],
                         NEXT_REVIEWER)

    def test_a_number_inside_a_message_is_no_provider_refusal(self):
        for text in ("worker 14031 exited", "thread 4031 failed", "1403 items"):
            with self.subTest(text=text):
                self.assertIsNone(gate_reviewers.blocking_until({"error": {"message": text}}))
        self.assertIsNotNone(gate_reviewers.blocking_until({"error": {"code": "403"}}))
        self.assertIsNotNone(gate_reviewers.blocking_until({"error": {"message": "status code 429"}}))
        self.assertIsNotNone(gate_reviewers.blocking_until(
            {"error": {"code": "rate_limit_exceeded", "message": "slow down"}}))

    def test_a_local_error_that_borrows_a_provider_word_is_no_refusal(self):
        for text in ("write failed: disk quota exceeded",
                     "fatal: Authentication failed for 'https://github.com/o/r'",
                     "error: 403 files could not be read"):
            with self.subTest(text=text):
                self.assertIsNone(gate_reviewers.blocking_until({"error": {"message": text}}))

    def test_the_provider_reasons_that_block(self):
        for text in ("You have no credits left", "usage limit reached",
                     "HTTP 429 Too Many Requests", "401 Unauthorized", "403 Forbidden"):
            with self.subTest(text=text):
                self.assertIsNotNone(gate_reviewers.blocking_until({"error": {"message": text}}))
        for text in ("syntax error", "the diff does not build"):
            with self.subTest(text=text):
                self.assertIsNone(gate_reviewers.blocking_until({"error": {"message": text}}))


class LateReadWindowTest(ReplayBase):
    """A failure read long after it happened holds only what is left.

    The recorded review: the error says the plan resets in 30 minutes, it
    happened at 10:00, and the queue first reads it at 10:25. The reset was
    10:30, so the block ends at 10:30 and not at 10:55, and a failure read
    after its window closed blocks nobody at all.
    """

    def test_a_failure_read_late_holds_the_reviewer_for_what_is_left(self):
        self.gate = gate_failed_ago(25 * 60)
        self.write_queue(heads={self.key: 4})
        self.run_gatekeep()
        records = self.blocked_records()
        self.assertEqual(list(records), [identity(CHAIN_HEAD)])
        # Five minutes of the window are left, not another thirty.
        self.assertAlmostEqual(records[identity(CHAIN_HEAD)]["until"] - time.time(),
                               300, delta=30)
        lines = [line for line in self.log_lines() if "blocked until" in line]
        self.assertEqual(len(lines), 1)

    def test_a_window_that_closed_before_the_read_blocks_nobody(self):
        # Failed 40 minutes ago, so the 30 minute reset it named ended already.
        self.gate = gate_failed_ago(40 * 60)
        self.write_queue(heads={self.key: {"id": 4, "retries": 0, "at": None,
                                           "givenUp": False}})
        out, _ = self.run_gatekeep()
        self.assertEqual(self.blocked_records(), {})
        self.assertEqual([line for line in self.log_lines() if "blocked" in line], [])
        # The reviewer is free, so the chain still starts where it always does
        # and the dead gate moves one place down it.
        self.assertEqual(coordq.reviewer_model([]), CHAIN_HEAD)
        self.assertEqual(coordq.starting_reviewer(), CHAIN_HEAD)
        items = self.gate_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["args"]["modelSelection"], NEXT_REVIEWER)
        self.assertNotIn("every gate reviewer is blocked", out)

    def test_a_window_with_no_stated_end_also_runs_from_the_failure(self):
        message = "usage limit reached"
        self.gate = gate_failed_ago(90 * 60, message)
        self.assertIsNone(gate_reviewers.blocking_until(self.gate))
        self.gate = gate_failed_ago(10 * 60, message)
        # Fifty minutes of the hour are left, not a fresh hour.
        self.assertAlmostEqual(gate_reviewers.blocking_until(self.gate) - time.time(),
                               3000, delta=30)

    def test_the_run_time_is_read_before_the_thread_time(self):
        # The thread was updated now, the run failed 25 minutes ago. The run
        # carries the error, so the run carries the clock too.
        self.gate = gate_failed_ago(25 * 60)
        self.assertAlmostEqual(gate_reviewers.blocking_until(self.gate) - time.time(),
                               300, delta=30)

    def test_a_failure_that_names_no_time_still_holds_its_stated_window(self):
        # A dispatch refused before any run exists says only what the provider
        # said, so there is no run clock and the window starts at this read.
        until = gate_reviewers.blocking_until({"error": {"message": NO_CREDITS}})
        self.assertAlmostEqual(until - time.time(), 1800, delta=30)
        until = gate_reviewers.blocking_until({"error": {"message": "usage limit"}})
        self.assertAlmostEqual(until - time.time(), 3600, delta=30)

    def test_a_local_window_is_clamped_to_this_read(self):
        # A run whose recorded end is in the future, because the two clocks
        # disagree, holds no longer than its window from this read.
        future = gate_failed_ago(-600)
        self.assertAlmostEqual(gate_reviewers.blocking_until(future) - time.time(),
                               1800, delta=30)

    def test_a_recorded_time_reads_as_epoch_seconds(self):
        self.assertEqual(gate_reviewers.parse_time("1970-01-01T00:01:40Z"), 100)
        self.assertEqual(gate_reviewers.parse_time("1970-01-01T00:01:40+00:00"), 100)
        self.assertEqual(gate_reviewers.parse_time(100.5), 100.5)
        for value in (None, "", "  ", "soon", True, False, {}, [], float("nan"),
                      float("inf")):
            with self.subTest(value=value):
                self.assertIsNone(gate_reviewers.parse_time(value))

    def test_the_same_failure_read_twice_holds_the_same_end(self):
        # A block written and then read again, after the queue record was lost
        # midway, must not move the end or print a second line.
        self.gate = gate_failed_ago(25 * 60)
        first = coordq.block_failed_reviewer(CHAIN_HEAD, self.gate)
        second = coordq.block_failed_reviewer(CHAIN_HEAD, self.gate)
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(self.blocked_records()[identity(CHAIN_HEAD)]["until"], first)
        lines = [line for line in self.log_lines() if "blocked until" in line]
        self.assertEqual(len(lines), 1)

    def test_a_block_that_never_ends_is_released(self):
        # A record whose end is not a finite time neither blocks nor expires
        # on its own, so it is read as ended and dropped like an expired one.
        now = time.time()
        for until in (float("nan"), float("inf"), "soon", True):
            with self.subTest(until=until):
                self.write_blocked({identity(CHAIN_HEAD): {"until": until, "at": now}})
                self.write_queue()
                self.run_gatekeep()
                self.assertEqual(self.blocked_records(), {})
                self.assertEqual(coordq.starting_reviewer(), CHAIN_HEAD)


if __name__ == "__main__":
    unittest.main()
