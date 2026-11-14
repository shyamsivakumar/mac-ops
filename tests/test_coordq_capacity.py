import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from tests.test_gatekeep_backstop_reviewer import load_coordq


class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.q = load_coordq()
        self.q.DIR = self.tmp.name
        self.q.live = lambda: 2
        self.q.cap = lambda: 6
        self.q.save({"next": 2, "items": [
            {"id": 1, "tool": "t3_thread_launch", "args": {},
             "priority": 0, "title": "queued"}]})

    def refill(self):
        candidates = [{"repository": {"nameWithOwner": "o/r"},
                       "number": n, "title": str(n)} for n in range(10)]
        with patch.object(self.q, "board_candidates", return_value=candidates), patch.object(
                self.q, "ticket_start", return_value=(0, "started")) as start:
            self.q.refill(argparse.Namespace(dry_run=False))
            return start.call_count

    def test_nonempty_queue_fills_only_three_slots_with_lagging_count(self):
        self.assertEqual(self.refill(), 3)

    def test_six_used_starts_nothing(self):
        self.q.live = lambda: 5
        self.assertEqual(self.refill(), 0)

    def test_exhausted_item_removed_reported_and_logged_once(self):
        data = self.q.load()
        data["items"][0].update(attempts=self.q.MAX_ATTEMPTS, last_error="missing projectId")
        self.q.save(data)
        self.q.drain()
        self.q.drain()
        self.assertEqual(self.q.load()["items"], [])
        out = io.StringIO()
        with patch.object(self.q, "load_counts", return_value={}), redirect_stdout(out):
            self.q.cmd_status(None)
        self.assertEqual(json.loads(out.getvalue())["failed"][0]["id"], 1)
        from pathlib import Path
        log = Path(self.tmp.name, "dispatch.log").read_text()
        self.assertEqual(log.count("DROPPED #1 after 3 attempts: missing projectId"), 1)
