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
import threading
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
ASTRA_GATE = {"providerInstanceId": "openai-api", "model": "openai/gpt-6.2-astra"}
LAST_GATE = {"providerInstanceId": "claudeAgent", "model": "claude-sonnet-5-5"}
DEAD_GATE = {"thread": {"status": "failed", **ASTRA_GATE},
             "items": [{"type": "user_message", "text": "review"}],
             "recentRuns": [{"executedModel": None}]}
DEAD_LAST_GATE = {"thread": {"status": "failed", **LAST_GATE},
                 "items": [{"type": "user_message", "text": "review"}],
                 "recentRuns": [{"executedModel": None}]}

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
    first_review = coordq.model_list.entries("review")[0]["selection"]
    if first_review != launched:
        raise AssertionError(f"ASTRA_GATE drifted from the first review entry: {first_review}")


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

    def fake_gh(self, endpoint):
        if endpoint == f"repos/{REPO}/pulls/7":
            return {"changed_files": 0}
        if endpoint.startswith(f"repos/{REPO}/pulls/7/files"):
            return []
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

    def test_a_dead_last_gate_is_not_requeued(self):
        coordq.call = lambda tool, args, rules=None: (0, json.dumps(DEAD_LAST_GATE))
        self.write_queue(heads={self.key: 4})
        out, _ = self.run_gatekeep()
        self.assertNotIn("regating", out)
        self.assertEqual(self.gate_items(), [])
        # The head record is a dict now: the dead last gate is not requeued
        # and the head is recorded as given up.
        self.assertEqual(self.read_queue()["gatedHeads"][self.key],
                         {"id": 4, "retries": 0, "at": None, "givenUp": True})


class GateRetryOnceTest(RetryLimitBase):
    """A gate with no exact verdict line moves once to the next reviewer."""

    def report(self, text, status="completed"):
        coordq.call = lambda tool, args, rules=None: (
            0, json.dumps({"thread": {"status": status, **ASTRA_GATE},
                           "items": [{"type": "assistant_message", "text": text}]}))

    def test_a_refused_verdict_is_not_a_verdict(self):
        self.report("Checked it.\nUnable to issue VERDICT: PASS")
        self.write_queue(heads={self.key: 4})
        out, _ = self.run_gatekeep()
        self.assertIn("regating o/r#7", out)

    def test_a_quoted_verdict_followed_by_a_failure_is_not_a_verdict(self):
        examples = ("Expected output was:\n\n    VERDICT: PASS\n\nI could not finish.",
                    "Expected output was:\n```\nVERDICT: PASS\n```\nI could not finish.")
        for text in examples:
            with self.subTest(text=text):
                self.report(text)
                self.write_queue(heads={self.key: 4})
                out, _ = self.run_gatekeep()
                self.assertIn("regating o/r#7", out)

    def test_a_stalled_thread_read_does_not_hold_the_block_lock(self):
        finished = []
        listed = coordq.model_list.entries("review")[1]["selection"]

        def stalled_read(tool, args, rules=None):
            blocker = threading.Thread(
                target=coordq.model_list.block_provider, args=(listed, time.time() + 600))
            blocker.start()
            blocker.join(3)
            finished.append(not blocker.is_alive())
            return 0, json.dumps(DEAD_GATE)
        coordq.call = stalled_read
        self.addCleanup(os.unlink, coordq.model_list.blocked_path())
        self.write_queue(heads={self.key: 4})
        self.run_gatekeep()
        self.assertEqual(finished, [True])

    def test_a_verdict_with_a_diagnostic_line_after_it_is_a_verdict(self):
        self.report("Bad.\nVERDICT: FAIL\nwarning: tool call timed out")
        self.write_queue(heads={self.key: 4})
        out, _ = self.run_gatekeep()
        self.assertNotIn("regating", out)
        self.assertEqual(self.gate_items(), [])

    def test_the_retry_is_one_queue_write(self):
        self.write_queue(heads={self.key: 4})
        saves = []
        real_save = coordq.save
        coordq.save = lambda queue: (saves.append(json.dumps(queue)), real_save(queue))[1]
        self.addCleanup(setattr, coordq, "save", real_save)
        self.run_gatekeep()
        self.assertTrue(all(self.key in json.loads(saved)["gatedHeads"] for saved in saves))
        self.assertEqual(len([saved for saved in saves if '"retryOf"' in saved]), len(saves))
        head = self.read_queue()["gatedHeads"][self.key]
        self.assertEqual((head["retries"], head["retryOf"]), (1, "gate-1"))

    def test_the_stale_receipt_does_not_queue_a_second_retry(self):
        self.write_queue(heads={self.key: {"id": 5, "retries": 1, "at": time.time(),
                                          "givenUp": False, "retryOf": "gate-1"}})
        out, _ = self.run_gatekeep()
        self.assertEqual(self.gate_items(), [])
        self.assertNotIn("regating", out)

    def test_a_block_after_the_selection_is_not_queued_on_a_fresh_head(self):
        self.write_queue()
        first = coordq.model_list.entries("review")[0]["selection"]
        real = coordq.gate_candidates

        def blocking(config):
            for event in real(config):
                coordq.model_list.block_provider(first, time.time() + 600)
                yield event
        coordq.gate_candidates = blocking
        self.addCleanup(setattr, coordq, "gate_candidates", real)
        self.addCleanup(os.unlink, coordq.model_list.blocked_path())
        self.run_gatekeep()
        chosen = self.gate_items()[0]["args"]["modelSelection"]
        self.assertFalse(coordq.model_list.same_selection(chosen, first))

    def test_a_second_dead_gate_is_given_up(self):
        self.write_queue(heads={self.key: {"id": 5, "retries": 1, "at": 0,
                                          "givenUp": False, "retryOf": "gate-0"}})
        out, _ = self.run_gatekeep()
        self.assertIn("gave up", out)
        self.assertEqual(self.gate_items(), [])

    def test_a_blocked_reviewer_is_skipped_on_the_retry(self):
        self.write_queue(heads={self.key: 4})
        second = coordq.model_list.entries("review")[1]["selection"]
        coordq.model_list.block_provider(second, time.time() + 600)
        self.addCleanup(os.unlink, coordq.model_list.blocked_path())
        self.run_gatekeep()
        chosen = self.gate_items()[0]["args"]["modelSelection"]
        self.assertFalse(coordq.model_list.same_selection(chosen, second))


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


if __name__ == "__main__":
    unittest.main()
