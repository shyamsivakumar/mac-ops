"""The action key of a board action.

The board prints a command that carries the key of the action it wants
(`overnight` builds it at overnight:3948-3949). The key belongs to one
queue item, so the same board action is never sent twice, and the key is
written into the dispatch log next to the item it started.
"""

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tests.test_gatekeep_backstop_reviewer import load_coordq

PAYLOAD = json.dumps({"threadId": "mcp:launch:one",
                       "message": "PR #1 at abc needs rebase: conflict."})
KEY = "rebase:shyamsivakumar/mac-ops#1:abc123"


class ActionKeyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.q = load_coordq()
        self.q.DIR = self.tmp.name
        self.q.cap = lambda: 6
        # A start only queues here, so the proof reads the item the start
        # wrote; a send holds no slot and would otherwise go out at once.
        self.q.live = lambda: 6
        self.q.save({"next": 1, "items": []})

    def start(self, key=None, payload=PAYLOAD):
        args = argparse.Namespace(args=payload, title=None, priority=800,
                                  tool="t3_thread_send", action_key=key)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch.object(self.q, "drain"):
            try:
                self.q.cmd_start(args)
            except SystemExit as e:
                return e.code, out.getvalue(), err.getvalue()
        return 0, out.getvalue(), err.getvalue()

    def test_the_key_is_stored_on_the_queued_item(self):
        code, out, err = self.start(KEY)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "queued #1")
        queue = self.q.load()
        self.assertEqual(queue["items"][0]["actionKey"], KEY)
        self.assertEqual(queue["actionKeys"], {KEY: {"id": 1, "state": "queued"}})

    def test_a_start_without_the_key_still_queues(self):
        code, out, err = self.start()
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "queued #1")
        queue = self.q.load()
        self.assertNotIn("actionKey", queue["items"][0])
        self.assertNotIn("actionKeys", queue)

    def test_the_same_key_is_refused_and_names_the_first_item(self):
        self.start(KEY)
        before = self.q.load()
        code, out, err = self.start(KEY)
        self.assertEqual(code, 1)
        self.assertIn(KEY, err)
        self.assertIn("#1", err)
        self.assertEqual(out.strip(), "")
        after = self.q.load()
        self.assertEqual(after["items"], before["items"])
        self.assertEqual(after["actionKeys"], {KEY: {"id": 1, "state": "queued"}})
        self.assertEqual(after["next"], before["next"])

    def test_a_dispatched_key_is_still_refused(self):
        self.start(KEY)
        # The dispatcher takes the item out of the queue and starts it.
        self.q.live = lambda: 0
        with patch.object(self.q, "active_thread_ids", return_value=set()), \
                patch.object(self.q, "call", return_value=(0, "{}")):
            self.q.drain()
        self.assertEqual(self.q.load()["items"], [])
        code, out, err = self.start(KEY)
        self.assertEqual(code, 1)
        self.assertIn("already dispatched", err)
        self.assertIn("#1", err)
        self.assertEqual(len(self.q.load()["items"]), 0)

    def test_a_key_without_an_item_id_stays_held(self):
        # A record the queue cannot read is still a key the queue took.
        # Releasing it would let the same board action be sent twice.
        queue = self.q.load()
        queue["actionKeys"] = {KEY: {"state": "queued"}}
        self.q.save(queue)
        code, out, err = self.start(KEY)
        self.assertEqual(code, 1)
        self.assertIn(KEY, err)
        self.assertEqual(self.q.load()["items"], [])

    def test_a_legacy_key_of_a_queued_item_is_read_as_queued(self):
        # A record written before the state was kept is a bare item id.
        # The item may still be waiting in the queue, so the state comes
        # from the queue and not from the shape of the record.
        queue = self.q.load()
        queue["items"] = [{"id": 1, "tool": "t3_thread_send",
                           "args": {"threadId": "mcp:launch:one"},
                           "priority": 800, "title": "board action",
                           "actionKey": KEY}]
        queue["actionKeys"] = {KEY: 1}
        self.q.save(queue)
        code, out, err = self.start(KEY)
        self.assertEqual(code, 1)
        self.assertIn("already queued", err)
        self.assertIn("#1", err)

    def test_a_legacy_key_of_a_gone_item_is_read_as_dispatched(self):
        queue = self.q.load()
        queue["actionKeys"] = {KEY: 7}
        self.q.save(queue)
        code, out, err = self.start(KEY)
        self.assertEqual(code, 1)
        self.assertIn("already dispatched", err)
        self.assertIn("#7", err)

    def test_a_legacy_key_keeps_its_state_after_a_dispatch(self):
        queue = self.q.load()
        queue["items"] = [{"id": 1, "tool": "t3_thread_send",
                           "args": {"threadId": "mcp:launch:one"},
                           "priority": 800, "title": "board action",
                           "actionKey": KEY}]
        queue["actionKeys"] = {KEY: 1}
        self.q.save(queue)
        self.q.live = lambda: 0
        with patch.object(self.q, "active_thread_ids", return_value=set()), \
                patch.object(self.q, "call", return_value=(0, "{}")):
            self.q.drain()
        self.assertEqual(self.q.load()["actionKeys"],
                         {KEY: {"id": 1, "state": "dispatched"}})
        code, out, err = self.start(KEY)
        self.assertEqual(code, 1)
        self.assertIn("already dispatched", err)

    def test_the_key_of_an_item_that_gave_up_is_released(self):
        self.start(KEY)
        # The item ran out of attempts and left the queue without ever
        # reaching the thread, so the board action is still open.
        queue = self.q.load()
        queue["items"][0]["attempts"] = self.q.MAX_ATTEMPTS
        self.q.save(queue)
        self.q.drain()
        self.assertEqual(self.q.load()["items"], [])
        self.assertEqual(self.q.load()["actionKeys"], {})
        code, out, err = self.start(KEY)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "queued #2")

    def test_the_key_of_a_dropped_item_is_released(self):
        self.start(KEY)
        self.q.cmd_drop(argparse.Namespace(id=1))
        self.assertEqual(self.q.load()["items"], [])
        self.assertEqual(self.q.load()["actionKeys"], {})
        code, out, err = self.start(KEY)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "queued #2")

    def test_another_head_is_another_key(self):
        self.start(KEY)
        code, out, err = self.start("rebase:shyamsivakumar/mac-ops#1:def456")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "queued #2")
        self.assertEqual(self.q.load()["actionKeys"],
                         {KEY: {"id": 1, "state": "queued"},
                          "rebase:shyamsivakumar/mac-ops#1:def456": {"id": 2, "state": "queued"}})

    def test_the_started_line_carries_the_key(self):
        self.start(KEY)
        self.q.live = lambda: 0
        with patch.object(self.q, "active_thread_ids", return_value=set()), \
                patch.object(self.q, "call", return_value=(0, "{}")):
            self.q.drain()
        log = Path(self.tmp.name, "dispatch.log").read_text()
        self.assertIn(f"started #1 t3_thread_send", log)
        self.assertIn(f"key {KEY}", log)

    def test_a_start_without_the_key_writes_no_key_in_the_log(self):
        self.start()
        self.q.live = lambda: 0
        with patch.object(self.q, "active_thread_ids", return_value=set()), \
                patch.object(self.q, "call", return_value=(0, "{}")):
            self.q.drain()
        log = Path(self.tmp.name, "dispatch.log").read_text()
        self.assertIn("started #1 t3_thread_send", log)
        self.assertNotIn(" key ", log)


if __name__ == "__main__":
    unittest.main()
