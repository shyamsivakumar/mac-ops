"""Tests for the reviewer of a gatekeep candidate.

`coordq` is a script without a .py suffix, so it is loaded by path. The
queue directory is a temporary one, so a proof never touches the live
queue.
"""
import argparse
import importlib.util
import io
import json
import os
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

REPO = "o/r"
HEAD = "a" * 40
CONFIG = {"repos": {REPO: {"key": "T", "projectId": "P"}}}
RECEIPT = {"kind": "receipt", "attempt": 1, "requestId": "req-1"}
COMMENT = {"user": {"login": "me"},
           "body": "attempt 1\n<!-- coordinator-ticket "
                   + json.dumps(RECEIPT)
                   + " -->"}

coordq = None
QUEUE_DIR = None
SAVED_COORDQ_DIR = None


def load_coordq():
    path = ROOT / "coordinator" / "bin" / "coordq"
    loader = SourceFileLoader("coordq_cli", str(path))
    spec = importlib.util.spec_from_loader("coordq_cli", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def setUpModule():
    """Point coordq at a temporary queue for the length of this module.

    `coordq` reads `COORDQ_DIR` when it is loaded, so the variable is set
    before the module is loaded and put back when the tests are done.
    """
    global coordq, QUEUE_DIR, SAVED_COORDQ_DIR
    SAVED_COORDQ_DIR = os.environ.get("COORDQ_DIR")
    QUEUE_DIR = tempfile.mkdtemp(prefix="coordq-gatekeep-")
    os.environ["COORDQ_DIR"] = QUEUE_DIR
    coordq = load_coordq()


def tearDownModule():
    if SAVED_COORDQ_DIR is None:
        os.environ.pop("COORDQ_DIR", None)
    else:
        os.environ["COORDQ_DIR"] = SAVED_COORDQ_DIR


class FakeRun:
    def __init__(self, stdout=""):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


class GatekeepBase(unittest.TestCase):
    """The board, the builder and the check of one pull request."""

    def setUp(self):
        self.saved = {name: getattr(coordq, name)
                      for name in ("gh_json", "load_receipts", "subprocess")}
        self.addCleanup(lambda: [setattr(coordq, name, value)
                                 for name, value in self.saved.items()])
        self.pr = {"draft": False, "number": 7, "head": {"sha": HEAD},
                   "body": f"Refs #9\nBuilder check: PASS {HEAD}\n"}
        coordq.subprocess = types.SimpleNamespace(
            run=lambda *a, **k: FakeRun("me\n"))
        coordq.load_receipts = lambda: {RECEIPT["requestId"]: "thread-1"}
        coordq.gh_json = self.fake_gh

    def fake_gh(self, endpoint):
        if endpoint.startswith(f"repos/{REPO}/pulls"):
            return [self.pr]
        if "/issues/" in endpoint and endpoint.endswith("/comments?per_page=100"):
            return [COMMENT]
        if endpoint.startswith(f"repos/{REPO}/commits/"):
            return []
        raise AssertionError(f"unexpected endpoint {endpoint}")


class GatekeepCandidateTest(GatekeepBase):
    """Every candidate is gated on Astra, whatever built it."""

    def candidates(self):
        errors = io.StringIO()
        with redirect_stderr(errors):
            events = list(coordq.gate_candidates(CONFIG))
        self.errors = errors.getvalue()
        return events

    def test_the_candidate_uses_astra(self):
        candidates = [e for e in self.candidates() if e["kind"] == "candidate"]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["args"]["modelSelection"],
                         {"instanceId": "codex", "model": "gpt-6-astra"})

    def test_the_builder_run_is_not_read_to_pick_the_reviewer(self):
        # The reviewer no longer follows the builder, so nothing reads the
        # builder thread of the pull request while choosing it.
        with patch.object(coordq, "call", side_effect=AssertionError("builder read")):
            candidates = [e for e in self.candidates() if e["kind"] == "candidate"]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["args"]["modelSelection"], coordq.ASTRA_MODEL)

    def test_no_line_about_the_builder_model_is_logged(self):
        self.candidates()
        self.assertEqual([line for line in self.errors.splitlines()
                          if line.startswith("backstop ")], [])

    def test_no_skip_is_reported(self):
        skips = [e for e in self.candidates() if e["kind"] == "skip"]
        self.assertEqual([e["reason"] for e in skips], [])

    def test_a_missing_builder_run_is_skipped(self):
        coordq.load_receipts = lambda: {}
        with patch.object(coordq, "builder_thread_for_issue", return_value=None):
            skips = [e for e in self.candidates() if e["kind"] == "skip"]
        self.assertEqual([e["reason"] for e in skips], ["builder run not found"])

    def test_a_pull_request_without_a_passing_check_is_not_gated(self):
        self.pr["body"] = "Refs #9\n"
        events = self.candidates()
        self.assertEqual([e for e in events if e["kind"] == "candidate"], [])


class GatekeepQueueTest(GatekeepBase):
    """Two gatekeep runs queue one gate for the same head."""

    def setUp(self):
        super().setUp()
        self.config = os.path.join(QUEUE_DIR, "gatekeep-config.json")
        with open(self.config, "w") as f:
            json.dump(CONFIG, f)
        queue_file = os.path.join(QUEUE_DIR, "queue.json")
        if os.path.exists(queue_file):
            os.remove(queue_file)

    def run_gatekeep(self):
        args = argparse.Namespace(config=self.config, dry_run=False)
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            coordq.cmd_gatekeep(args)
        return out.getvalue()

    def test_two_runs_queue_one_gate(self):
        self.run_gatekeep()
        self.run_gatekeep()
        with open(os.path.join(QUEUE_DIR, "queue.json")) as f:
            queue = json.load(f)
        gates = [item for item in queue["items"] if item["tool"] == "t3_thread_launch"]
        self.assertEqual(len(gates), 1)
        self.assertEqual(gates[0]["args"]["modelSelection"],
                         {"instanceId": "codex", "model": "gpt-6-astra"})

    def test_a_gated_head_is_not_stuck(self):
        for _ in range(coordq.STUCK_COUNT):
            self.run_gatekeep()
        with open(os.path.join(QUEUE_DIR, "gatekeep-stuck.txt")) as f:
            self.assertEqual(f.read(), "")
        with open(os.path.join(QUEUE_DIR, "queue.json")) as f:
            queue = json.load(f)
        self.assertEqual(queue.get("gatekeepSkips", {}), {})


if __name__ == "__main__":
    unittest.main()
