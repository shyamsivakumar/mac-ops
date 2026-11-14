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

    def queue_sends(self):
        self.q.save({"next": 31, "items": [
            {"id": n, "tool": "t3_thread_send", "args": {"threadId": str(n)},
             "priority": 0, "title": "burst"} for n in range(1, 31)]})
        self.q.live = lambda: 0

    def test_burst_with_stale_total_and_individual_visibility(self):
        self.queue_sends()
        visible = set()
        started = []
        def start(tool, args, rules=None):
            started.append(args["threadId"])
            self.assertLessEqual(len(visible) + len(self.q.load()["reserved"]), 6)
            return 0, "{}"
        with patch.object(self.q, "active_thread_ids", side_effect=lambda: set(visible)), patch.object(self.q, "call", side_effect=start):
            self.q.drain()
            self.assertEqual(len(started), 6)
            for thread in started[:]:
                visible.add(thread)
                self.q.drain()
                self.assertEqual(len(started), 6)
                self.assertEqual(len(visible) + len(self.q.load()["reserved"]), 6)

    def test_expired_reservation_does_not_block(self):
        self.queue_sends()
        data = self.q.load()
        data["reserved"] = {"old": self.q.time.time() - 601}
        self.q.save(data)
        with patch.object(self.q, "active_thread_ids", return_value=set()), patch.object(self.q, "call", return_value=(0, "{}")) as start:
            self.q.drain()
        self.assertEqual(start.call_count, 6)
        self.assertNotIn("old", self.q.load()["reserved"])

    def test_failed_start_releases_reservation(self):
        self.queue_sends()
        data = self.q.load()
        data["items"] = data["items"][:1]
        self.q.save(data)
        with patch.object(self.q, "active_thread_ids", return_value=set()), patch.object(self.q, "call", return_value=(1, "failed")):
            self.q.drain()
        self.assertEqual(self.q.load()["reserved"], {})

    def test_pre_steps_reserve_their_own_slots(self):
        self.queue_sends()
        data = self.q.load()
        data["items"] = data["items"][:1]
        data["items"][0]["pre"] = [{"tool": "t3_thread_send", "args": {"threadId": "pre"}}]
        self.q.save(data)
        with patch.object(self.q, "active_thread_ids", return_value=set()), patch.object(self.q, "call", side_effect=[(0, "{}"), (1, "failed"), (1, "failed"), (1, "failed")]):
            self.q.drain()
        self.assertEqual(len(self.q.load()["reserved"]), 1)
        self.assertEqual(set(self.q.load()["reservedThreads"].values()), {"pre"})

    def queue_launch(self):
        self.q.save({"next": 2, "items": [
            {"id": 7, "tool": "t3_thread_launch", "args": {}, "priority": 0,
             "title": "launch"}]})
        self.q.live = lambda: 0

    def test_successful_launch_holds_its_slot_until_the_thread_is_visible(self):
        self.queue_launch()
        reply = json.dumps({"threadId": "mcp:launch:one"})
        with patch.object(self.q, "active_thread_ids", return_value=set()), patch.object(
                self.q, "thread_status", return_value="running"), patch.object(
                self.q, "call", return_value=(0, reply)):
            self.q.drain()
        queue = self.q.load()
        self.assertIn("7", queue["reserved"])
        self.assertEqual(queue["reservedThreads"]["7"], "launch:mcp:launch:one")
        self.assertEqual(queue["items"], [])

    def test_terminal_thread_releases_a_launch_slot_that_was_never_seen_live(self):
        self.q.save({"next": 2, "items": [],
                     "reserved": {"7": self.q.time.time()},
                     "reservedThreads": {"7": "launch:mcp:launch:one"}})
        self.q.live = lambda: 0
        with patch.object(self.q, "active_thread_ids", return_value=set()), patch.object(
                self.q, "thread_status", return_value="completed"):
            self.q.drain()
        queue = self.q.load()
        self.assertEqual(queue["reserved"], {})
        self.assertEqual(queue["reservedThreads"], {})
        from pathlib import Path
        log = Path(self.tmp.name, "dispatch.log").read_text()
        self.assertIn("released reservation #7: thread mcp:launch:one is completed", log)

    def test_unfinished_thread_keeps_a_launch_slot_that_was_never_seen_live(self):
        # Elapsed time alone must not free the slot: only a terminal status does.
        self.q.save({"next": 2, "items": [],
                     "reserved": {"7": self.q.time.time() - 300},
                     "reservedThreads": {"7": "launch:mcp:launch:one"}})
        self.q.live = lambda: 0
        with patch.object(self.q, "active_thread_ids", return_value=set()), patch.object(
                self.q, "thread_status", return_value="waiting"):
            self.q.drain()
        self.assertIn("7", self.q.load()["reserved"])

    def test_launch_burst_does_not_overshoot_the_cap_with_a_lagging_count(self):
        self.q.save({"next": 40, "items": [
            {"id": n, "tool": "t3_thread_launch", "args": {}, "priority": 0,
             "title": "burst"} for n in range(1, 31)]})
        self.q.live = lambda: 0
        calls = []
        def start(tool, args, rules=None):
            calls.append(args)
            return 0, json.dumps({"threadId": f"mcp:launch:{len(calls)}"})
        with patch.object(self.q, "active_thread_ids", return_value=set()), patch.object(
                self.q, "thread_status", return_value="running"), patch.object(
                self.q, "call", side_effect=start):
            self.q.drain()
        self.assertEqual(len(calls), 6)

    def test_launch_without_thread_id_keeps_its_reservation(self):
        self.queue_launch()
        with patch.object(self.q, "active_thread_ids", return_value=set()), patch.object(
                self.q, "call", return_value=(0, "{}")):
            self.q.drain()
        queue = self.q.load()
        self.assertIn("7", queue["reserved"])
        from pathlib import Path
        log = Path(self.tmp.name, "dispatch.log").read_text()
        self.assertIn("reservation #7 retained", log)
