"""Replay tests for the gate that falls back to the next reviewer.

A gate run that ends without a verdict moves once to the next unblocked
reviewer of the same head, and the choice and the queue item happen under
the lock the provider block store uses, so a block recorded in between
cannot queue a blocked reviewer. A run that ends with a verdict is never
retried elsewhere.

`coordq` is a script without a .py suffix, so it is loaded by path. The
queue directory is a temporary one, so a test never touches the live
queue or the live block store.
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
CONFIG = {"repos": {REPO: {"key": "T", "projectId": "P"}}}
RECEIPT = {"kind": "receipt", "attempt": 1, "requestId": "req-1"}
COMMENT = {"user": {"login": "me"},
           "body": "attempt 1\n<!-- coordinator-ticket "
                   + json.dumps(RECEIPT)
                   + " -->"}
BUILDER_THREAD = {"providerInstanceId": "minimax", "model": "minimax/MiniMax-M3.1-Flash"}
BUILDER_RUNS = [{"executedModel": "minimax/MiniMax-M3.1-Flash"}]

coordq = None
QUEUE_DIR = None
SAVED_COORDQ_DIR = None
FIRST = None
SECOND = None
THIRD = None


def load_coordq():
    path = ROOT / "coordinator" / "bin" / "coordq"
    loader = SourceFileLoader("coordq_reviewer_fallback", str(path))
    spec = importlib.util.spec_from_loader("coordq_reviewer_fallback", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def setUpModule():
    global coordq, QUEUE_DIR, SAVED_COORDQ_DIR, FIRST, SECOND, THIRD
    SAVED_COORDQ_DIR = os.environ.get("COORDQ_DIR")
    QUEUE_DIR = tempfile.mkdtemp(prefix="coordq-reviewer-fallback-")
    os.environ["COORDQ_DIR"] = QUEUE_DIR
    coordq = load_coordq()
    entries = coordq.model_list.entries("review")
    FIRST, SECOND, THIRD = (e["selection"] for e in entries[:3])


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


def dead_gate(reviewer=None):
    """A gate that died without a verdict.

    A gate that records no reviewer at all is a gate that died before it
    started, so `reviewer=None` leaves the provider and the model out.
    """
    thread = {"status": "failed"}
    if reviewer:
        thread.update(providerInstanceId=reviewer["instanceId"], model=reviewer["model"])
    return {"thread": thread,
            "items": [{"type": "user_message", "text": "review"}],
            "recentRuns": [{"executedModel": None}]}


class FallbackBase(unittest.TestCase):
    """One pull request whose gate died without a verdict."""

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
        coordq.call = lambda tool, args, rules=None: (0, json.dumps(dead_gate(FIRST)))
        self.config = os.path.join(QUEUE_DIR, "gatekeep-config.json")
        with open(self.config, "w") as f:
            json.dump(CONFIG, f)
        self.blocked_file = os.path.join(QUEUE_DIR, "providers-blocked.json")
        self.addCleanup(self.clear_block)

    def clear_block(self):
        if os.path.exists(self.blocked_file):
            os.remove(self.blocked_file)

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

    def write_block(self, identity):
        with open(self.blocked_file, "w") as f:
            json.dump({"blocked": {identity: {"until": time.time() + 3600}}}, f)

    def run_gatekeep(self, dry_run=False):
        args = argparse.Namespace(config=self.config, dry_run=dry_run)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            coordq.cmd_gatekeep(args)
        return out.getvalue(), err.getvalue()


class VerdictlessFallbackTest(FallbackBase):
    """A gate that died without a verdict moves down the chain once."""

    def test_the_next_reviewer_is_queued_for_the_same_head(self):
        self.write_queue(heads={self.key: {"id": 4, "retries": 0, "at": None,
                                           "givenUp": False, "reviewer": coordq.model_list.identity(FIRST)}})
        out, _ = self.run_gatekeep()
        self.assertIn("regating o/r#7", out)
        items = self.gate_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["args"]["modelSelection"], SECOND)
        heads = self.read_queue()["gatedHeads"]
        self.assertEqual(heads[self.key]["retries"], 1)
        self.assertEqual(heads[self.key]["reviewer"], coordq.model_list.identity(SECOND))

    def test_a_gate_with_a_verdict_is_never_retried_elsewhere(self):
        coordq.call = lambda tool, args, rules=None: (
            0, json.dumps({"thread": {"status": "completed"},
                           "items": [{"type": "assistant_message", "text": "VERDICT: PASS"}]}))
        self.write_queue(heads={self.key: {"id": 4, "retries": 0, "at": None,
                                           "givenUp": False, "reviewer": coordq.model_list.identity(FIRST)}})
        out, _ = self.run_gatekeep()
        self.assertEqual(self.gate_items(), [])
        self.assertNotIn("regating", out)

    def test_a_gate_that_recorded_no_reviewer_still_moves_down(self):
        coordq.call = lambda tool, args, rules=None: (0, json.dumps(dead_gate()))
        self.write_queue(heads={self.key: {"id": 4, "retries": 0, "at": None,
                                           "givenUp": False, "reviewer": coordq.model_list.identity(FIRST)}})
        self.run_gatekeep()
        items = self.gate_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["args"]["modelSelection"], SECOND)

    def test_the_head_gets_one_gate_and_one_reviewer(self):
        self.write_queue(heads={self.key: {"id": 4, "retries": 0, "at": None,
                                           "givenUp": False, "reviewer": coordq.model_list.identity(FIRST)}})
        self.run_gatekeep()
        self.run_gatekeep()
        # One gate for the head: the second run waits for the backoff
        # instead of queueing a second gate for the same head.
        self.assertEqual(len(self.gate_items()), 1)
        heads = self.read_queue()["gatedHeads"]
        self.assertEqual(heads[self.key]["retries"], 1)
        self.assertEqual(heads[self.key]["reviewer"], coordq.model_list.identity(SECOND))


class BlockedReviewerTest(FallbackBase):
    """A blocked reviewer is never queued."""

    def test_a_blocked_reviewer_is_skipped(self):
        self.write_block(coordq.model_list.identity(SECOND))
        self.write_queue(heads={self.key: {"id": 4, "retries": 0, "at": None,
                                           "givenUp": False, "reviewer": coordq.model_list.identity(FIRST)}})
        self.run_gatekeep()
        items = self.gate_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["args"]["modelSelection"], THIRD)

    def test_a_block_recorded_before_the_choice_is_seen(self):
        """The store's writer and the gate take the same lock.

        The writer holds the lock and records the block, so the gate waits
        for it and then reads the block it wrote. The blocked reviewer is
        never queued.
        """
        held = threading.Event()
        release = threading.Event()

        def writer():
            with coordq.model_list.blocked_lock():
                self.write_block(coordq.model_list.identity(SECOND))
                held.set()
                release.wait(10)

        thread = threading.Thread(target=writer)
        thread.start()
        self.assertTrue(held.wait(10))
        self.write_queue(heads={self.key: {"id": 4, "retries": 0, "at": None,
                                           "givenUp": False, "reviewer": coordq.model_list.identity(FIRST)}})
        result = []

        def run():
            result.append(self.run_gatekeep())

        gate = threading.Thread(target=run)
        gate.start()
        time.sleep(0.2)
        release.set()
        gate.join(30)
        thread.join(30)
        items = self.gate_items()
        self.assertEqual(len(items), 1)
        self.assertNotEqual(items[0]["args"]["modelSelection"], SECOND)
        self.assertEqual(items[0]["args"]["modelSelection"], THIRD)

    def test_the_queue_item_is_appended_under_the_store_lock(self):
        """The lock is held while the item is appended."""
        held = []

        class Recorder:
            def __enter__(self):
                held.append(True)
                return self

            def __exit__(self, *exc):
                held.pop()
                return False

        original = coordq.model_list.blocked_lock
        coordq.model_list.blocked_lock = lambda: Recorder()
        self.addCleanup(lambda: setattr(coordq.model_list, "blocked_lock", original))
        seen = []
        original_save = coordq.save

        def save(queue):
            seen.append(bool(held))
            original_save(queue)

        coordq.save = save
        self.addCleanup(lambda: setattr(coordq, "save", original_save))
        self.write_queue(heads={self.key: {"id": 4, "retries": 0, "at": None,
                                           "givenUp": False, "reviewer": coordq.model_list.identity(FIRST)}})
        self.run_gatekeep()
        self.assertTrue(seen)
        self.assertTrue(all(seen[:2]), f"the queue was written without the store lock: {seen}")


if __name__ == "__main__":
    unittest.main()
