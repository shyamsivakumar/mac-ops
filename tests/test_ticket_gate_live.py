"""Tests for the duplicate-gate pre-check in the ticket CLI.

The CLI is a script without a .py suffix, so it is loaded by path.
"""
import importlib.util
import json
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The schema of the T3 tool caps the page size. A larger value is refused by
# the server, which stopped the gate before any of the real checks ran.
T3_THREAD_LIST_MAX_LIMIT = 100


def load_ticket():
    path = ROOT / "coordinator" / "bin" / "ticket"
    loader = SourceFileLoader("ticket_cli_gate_live", str(path))
    spec = importlib.util.spec_from_loader("ticket_cli_gate_live", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


ticket = load_ticket()

TITLE = "FFT-1 review #442 abcdef12"
GATE_ID = "gate:shyamsivakumar/fantasy-football-toolkit#442:abcdef12"


class GateLiveTest(unittest.TestCase):
    """The pre-check lists live threads and refuses a second gate on the head."""

    def setUp(self):
        self.queue_dir = tempfile.mkdtemp(prefix="ticket-gate-live-")
        self.addCleanup(self._remove_queue)
        self.saved_queue_dir = ticket.QUEUE_DIR
        ticket.QUEUE_DIR = self.queue_dir
        self.addCleanup(lambda: setattr(ticket, "QUEUE_DIR", self.saved_queue_dir))
        self.saved_t3_call = ticket.t3_call
        self.addCleanup(lambda: setattr(ticket, "t3_call", self.saved_t3_call))
        self.calls = []
        self.threads = []

        def fake_t3_call(tool, args):
            self.calls.append((tool, args))
            if tool == "t3_thread_list":
                return {"threads": self.threads}
            raise AssertionError(f"unexpected tool {tool}")

        ticket.t3_call = fake_t3_call

    def _remove_queue(self):
        for name in ("queue.json", "dispatch-receipts.json"):
            path = Path(self.queue_dir) / name
            if path.exists():
                path.unlink()
        Path(self.queue_dir).rmdir()

    def write(self, name, payload):
        (Path(self.queue_dir) / name).write_text(json.dumps(payload))

    def test_the_pre_check_never_asks_for_more_than_the_schema_maximum(self):
        self.assertIsNone(ticket.gate_live(TITLE, GATE_ID))
        listed = [args for tool, args in self.calls if tool == "t3_thread_list"]
        self.assertEqual(len(listed), 1)
        for args in listed:
            self.assertLessEqual(args["limit"], T3_THREAD_LIST_MAX_LIMIT)
        self.assertEqual(listed[0]["limit"], T3_THREAD_LIST_MAX_LIMIT)

    def test_a_live_thread_with_the_same_title_refuses(self):
        self.threads = [{"threadId": "T1", "status": "running", "title": TITLE}]
        live = ticket.gate_live(TITLE, GATE_ID)
        self.assertEqual(live, "thread T1 is running")

    def test_a_queued_gate_refuses_before_the_thread_list(self):
        self.write("queue.json", {"items": [{"id": 7, "args": {"clientRequestId": GATE_ID}}]})
        live = ticket.gate_live(TITLE, GATE_ID)
        self.assertEqual(live, "queued as coordq #7")
        self.assertEqual([tool for tool, _ in self.calls], [])

    def test_a_recorded_head_refuses_before_the_thread_list(self):
        self.write("queue.json", {"items": [], "gatedHeads": {GATE_ID: 9}})
        live = ticket.gate_live(TITLE, GATE_ID)
        self.assertEqual(live, "a gate for this head is already recorded as coordq #9")
        self.assertEqual([tool for tool, _ in self.calls], [])

    def test_a_receipt_refuses_before_the_thread_list(self):
        self.write("dispatch-receipts.json", {GATE_ID: "T2"})
        live = ticket.gate_live(TITLE, GATE_ID)
        self.assertEqual(live, "a gate thread already ran for this head (thread T2)")
        self.assertEqual([tool for tool, _ in self.calls], [])


if __name__ == "__main__":
    unittest.main()
