"""One message is one queue item.

On the night of 2026-11-17 the queue filled with the same message twice:
the lane driver queued every "MO#N gate findings" and "MO#N check" again
on the next pass, and a started item left no trace in the queue, so the
next pass could not see it. The queue keeps the record of a started
message now, and a start whose title and target the queue already holds is
refused.
"""

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from tests.test_gatekeep_backstop_reviewer import load_coordq

TITLE = "MO#544 gate findings"
THREAD = "mcp:launch:builder"
KEY = "fix:o/r#544:aaa"


class MessageDedupeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.q = load_coordq()
        self.q.DIR = self.tmp.name
        self.q.cap = lambda: 6
        # The queue is full, so a refused start never dispatches anything.
        self.q.live = lambda: 6
        self.q.save({"next": 1, "items": []})

    def start(self, title=TITLE, payload=None, key=None):
        payload = payload or json.dumps({"threadId": THREAD, "message": "fix the findings"})
        args = argparse.Namespace(args=payload, title=title, priority=800,
                                  tool="t3_thread_send", action_key=key)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stderr(err):
            try:
                self.q.cmd_start(args)
            except SystemExit as e:
                return e.code, err.getvalue()
        return 0, err.getvalue()

    def test_the_same_message_is_refused_while_it_waits(self):
        self.assertEqual(self.start()[0], 0)
        code, err = self.start()
        self.assertEqual(code, 1)
        self.assertIn("refused: duplicate message", err)
        self.assertIn(TITLE, err)
        self.assertIn(THREAD, err)
        self.assertIn("#1", err)
        self.assertEqual(len(self.q.load()["items"]), 1)

    def test_two_untitled_messages_to_one_thread_are_two_messages(self):
        # The finding: an untitled send carries its thread id as its display
        # title, which is not a message identity. Two callers can send two
        # different instructions to one thread, and neither is the other's
        # duplicate.
        first = self.start(payload=json.dumps({"threadId": THREAD, "message": "one"}),
                           title=None)
        second = self.start(payload=json.dumps({"threadId": THREAD, "message": "two"}),
                            title=None)
        self.assertEqual(first[0], 0, first[1])
        self.assertEqual(second[0], 0, second[1])
        items = self.q.load()["items"]
        self.assertEqual([i["args"]["message"] for i in items], ["one", "two"])
        self.assertEqual([i["title"] for i in items], [THREAD, THREAD])
        self.assertEqual([i["messageTitle"] for i in items], ["", ""])

    def test_a_queued_item_written_before_the_identity_was_kept_still_counts(self):
        # An item in the queue from the older code has no messageTitle; its
        # title was supplied by its caller, so it still suppresses a repeat.
        self.q.save({"next": 2, "items": [{"id": 1, "tool": "t3_thread_send",
                                           "args": {"threadId": THREAD, "message": "old"},
                                           "priority": 800, "title": TITLE}]})
        with patch.object(self.q, "read_rules", return_value="rules"):
            code, err = self.start()
        self.assertEqual(code, 1)
        self.assertIn("refused: duplicate message", err)

    def test_another_thread_is_another_message(self):
        self.assertEqual(self.start()[0], 0)
        other = json.dumps({"threadId": "mcp:launch:other", "message": "fix the findings"})
        code, err = self.start(payload=other)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.q.load()["items"]), 2)

    def test_another_title_is_another_message(self):
        self.assertEqual(self.start()[0], 0)
        code, err = self.start(title="MO#544 check")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.q.load()["items"]), 2)

    def test_a_started_message_counts_while_its_thread_is_live(self):
        self.q.save({"next": 2, "items": [],
                     "started": [{"id": 1, "title": TITLE, "target": THREAD,
                                  "thread": THREAD, "actionKey": "", "at": self.q.time.time()}]})
        with patch.object(self.q, "active_thread_ids", return_value={THREAD}):
            code, err = self.start()
        self.assertEqual(code, 1)
        self.assertIn("already started as coordq #1", err)
        self.assertEqual(self.q.load()["items"], [])

    def test_a_started_message_whose_thread_stopped_goes_out(self):
        # The builder finished the work, so the message it took is spent and
        # the next pass may queue it again.
        self.q.save({"next": 2, "items": [],
                     "started": [{"id": 1, "title": TITLE, "target": THREAD,
                                  "thread": THREAD, "actionKey": "", "at": self.q.time.time()}]})
        with patch.object(self.q, "active_thread_ids", return_value=set()):
            code, err = self.start()
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.q.load()["items"]), 1)

    def test_an_old_started_record_still_counts_while_its_thread_is_live(self):
        # Ticket #544 counts a running item: an age past the record timeout
        # must not let a second copy of the message start a second thread.
        self.q.save({"next": 2, "items": [],
                     "started": [{"id": 1, "title": TITLE, "target": THREAD,
                                  "thread": THREAD, "actionKey": "",
                                  "at": self.q.time.time() - self.q.MESSAGE_TTL - 1}]})
        with patch.object(self.q, "active_thread_ids", return_value={THREAD}):
            code, err = self.start()
        self.assertEqual(code, 1)
        self.assertIn("already started as coordq #1", err)
        self.assertEqual(self.q.load()["items"], [])

    def test_an_old_started_record_whose_thread_is_gone_is_forgotten(self):
        self.q.save({"next": 2, "items": [],
                     "started": [{"id": 1, "title": TITLE, "target": THREAD,
                                  "thread": THREAD, "actionKey": "",
                                  "at": self.q.time.time() - self.q.MESSAGE_TTL - 1}]})
        with patch.object(self.q, "active_thread_ids", return_value=set()):
            code, err = self.start()
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.q.load()["items"]), 1)
        self.assertEqual(self.q.load()["started"], [])

    def test_an_old_started_record_survives_an_unreadable_thread_list(self):
        self.q.save({"next": 2, "items": [],
                     "started": [{"id": 1, "title": TITLE, "target": THREAD,
                                  "thread": THREAD, "actionKey": "",
                                  "at": self.q.time.time() - self.q.MESSAGE_TTL - 1}]})
        with patch.object(self.q, "active_thread_ids", side_effect=RuntimeError("no t3")):
            code, err = self.start()
        self.assertEqual(code, 1)
        self.assertIn("refused: duplicate message", err)
        self.assertEqual(len(self.q.load()["started"]), 1)

    def test_an_unreadable_thread_list_still_refuses(self):
        # A refused start costs one attempt; a second copy of the message
        # costs a second thread on the same work.
        self.q.save({"next": 2, "items": [],
                     "started": [{"id": 1, "title": TITLE, "target": THREAD,
                                  "thread": THREAD, "actionKey": "", "at": self.q.time.time()}]})
        with patch.object(self.q, "active_thread_ids", side_effect=RuntimeError("no t3")):
            code, err = self.start()
        self.assertEqual(code, 1)
        self.assertIn("refused: duplicate message", err)

    def launch(self, request_id, title=TITLE):
        args = argparse.Namespace(
            args=json.dumps({"projectId": "fixture", "title": title, "message": "fix",
                             "modelSelection": {"instanceId": "codex", "model": "gpt-6.1-sol"},
                             "clientRequestId": request_id}),
            title=None, priority=800, tool="t3_thread_launch", action_key=None)
        err = io.StringIO()
        with patch.object(self.q, "read_rules", return_value="rules"), redirect_stderr(err):
            try:
                self.q.cmd_start(args)
            except SystemExit as e:
                return e.code, err.getvalue()
        return 0, err.getvalue()

    def test_a_launch_names_its_work_by_its_client_request(self):
        # A launch has no thread yet, so two launches for the same head are
        # the same message, and a launch for another head is another message.
        self.assertEqual(self.launch("fix:o/r#544:aaa")[0], 0)
        code, err = self.launch("fix:o/r#544:aaa")
        self.assertEqual(code, 1)
        self.assertIn("refused: duplicate message", err)
        self.assertEqual(self.launch("fix:o/r#544:bbb")[0], 0)

    def test_two_launches_with_no_target_are_not_one_message(self):
        # The gate finding: a launch without a client request has no target,
        # so two launches with the same title and different projects are two
        # launches. Refusing the second would drop work the queue was asked
        # to start.
        first = self.launch_payload("project-one")
        second = self.launch_payload("project-two")
        self.assertEqual(self.launch_no_request(first)[0], 0)
        code, err = self.launch_no_request(second)
        self.assertEqual(code, 0, err)
        items = self.q.load()["items"]
        self.assertEqual([i["args"]["projectId"] for i in items],
                         ["project-one", "project-two"])

    def test_a_board_action_key_still_guards_a_message_with_no_target(self):
        # The action key is the identity when the message carries one, so a
        # keyless launch is allowed and a repeated key is still refused.
        payload = self.launch_payload("project-one")
        self.assertEqual(self.launch_no_request(payload, key=KEY)[0], 0)
        code, err = self.launch_no_request(payload, key=KEY)
        self.assertEqual(code, 1)
        self.assertIn(KEY, err)
        self.assertEqual(len(self.q.load()["items"]), 1)

    def launch_payload(self, project_id, title=TITLE):
        return json.dumps({"projectId": project_id, "title": title, "message": "work",
                           "modelSelection": {"instanceId": "codex", "model": "gpt-6.1-sol"}})

    def launch_no_request(self, payload, key=None):
        args = argparse.Namespace(args=payload, title=None, priority=800,
                                  tool="t3_thread_launch", action_key=key)
        err = io.StringIO()
        with patch.object(self.q, "read_rules", return_value="rules"), redirect_stderr(err):
            try:
                self.q.cmd_start(args)
            except SystemExit as e:
                return e.code, err.getvalue()
        return 0, err.getvalue()

    def test_the_dispatch_records_the_started_message(self):
        self.q.live = lambda: 0
        # The whole test runs against the stub dispatcher: the first start
        # drains too, and a real drain would send the message.
        with patch.object(self.q, "active_thread_ids", return_value=set()), patch.object(
                self.q, "call", return_value=(0, "{}")):
            self.assertEqual(self.start()[0], 0)
        queue = self.q.load()
        self.assertEqual(queue["items"], [])
        self.assertEqual(queue["started"][0]["title"], TITLE)
        self.assertEqual(queue["started"][0]["target"], THREAD)
        self.assertEqual(queue["started"][0]["thread"], THREAD)
        # The same message is refused now that its thread has it.
        with patch.object(self.q, "active_thread_ids", return_value={THREAD}):
            self.assertEqual(self.start()[0], 1)


if __name__ == "__main__":
    unittest.main()
