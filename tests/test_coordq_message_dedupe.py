"""One message is one queue item.

On the night of 2026-11-17 the queue filled with the same message twice:
the lane driver queued every "MO#N gate findings" and "MO#N check" again
on the next pass, and a started item left no trace in the queue, so the
next pass could not see it. The queue keeps the record of a started
message now, and a start whose title and target the queue already holds is
refused.
"""

import argparse
import contextlib
import importlib.util
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from tests.test_gatekeep_backstop_reviewer import load_coordq

ROOT = Path(__file__).resolve().parents[1]

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

    def test_a_legacy_untitled_thread_id_title_is_not_an_identity(self):
        # The finding: an item written before the identity was kept stored the
        # thread id as its display title for an untitled send. That is not the
        # caller's title, so a new message explicitly titled with the thread id
        # is not a copy of it.
        self.q.save({"next": 2, "items": [{"id": 1, "tool": "t3_thread_send",
                                           "args": {"threadId": THREAD, "message": "old"},
                                           "priority": 800, "title": THREAD}]})
        code, err = self.start(title=THREAD)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.q.load()["items"]), 2)

    def test_a_started_record_added_after_the_thread_read_counts_as_running(self):
        # The list is read before the lock, so a record another start writes
        # while it is being read is not covered by it: the message it names has
        # just been taken, and this one is its copy.
        self.q.save({"next": 2, "items": [], "started": [{"id": 0, "title": "older",
                                                          "target": "other", "thread": "other",
                                                          "actionKey": "",
                                                          "at": self.q.time.time()}]})

        def read_live():
            queue = self.q.load()
            queue["started"].append({"id": 1, "title": TITLE, "target": THREAD,
                                     "thread": THREAD, "actionKey": "",
                                     "at": self.q.time.time()})
            self.q.save(queue)
            return set()

        with patch.object(self.q, "active_thread_ids", side_effect=read_live), \
                patch.object(self.q, "thread_status", return_value="completed"):
            code, err = self.start()
        self.assertEqual(code, 1)
        self.assertIn("refused: duplicate message", err)

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

    def test_a_different_action_key_does_not_make_a_second_copy(self):
        # The finding: two callers with different action keys and the same
        # title and target were queued twice. The title and the target name the
        # message; the key names one board action, not a second message.
        self.assertEqual(self.start(key="fix:o/r#544:aaa")[0], 0)
        code, err = self.start(key="fix:o/r#544:bbb")
        self.assertEqual(code, 1)
        self.assertIn("refused: duplicate message", err)
        self.assertEqual(len(self.q.load()["items"]), 1)

    def test_a_different_action_key_does_not_make_a_second_copy_when_running(self):
        self.q.save({"next": 2, "items": [],
                     "started": [{"id": 1, "title": TITLE, "target": THREAD,
                                  "thread": THREAD, "actionKey": "fix:o/r#544:aaa",
                                  "at": self.q.time.time()}]})
        with patch.object(self.q, "active_thread_ids", return_value={THREAD}):
            code, err = self.start(key="fix:o/r#544:bbb")
        self.assertEqual(code, 1)
        self.assertIn("refused: duplicate message", err)
        self.assertEqual(self.q.load()["items"], [])

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

    def test_a_launch_whose_slot_is_still_reserved_is_not_queued_again(self):
        # The finding: a launch learns its thread only after the call, so its
        # started record can exist before the thread list shows it. While the
        # queue holds the reservation for that launch, a second pass must not
        # queue the same launch again.
        request = "fix:o/r#544:aaa"
        self.q.save({"next": 2, "items": [],
                     "started": [{"id": 1, "title": TITLE, "target": request,
                                  "thread": "mcp:launch:new", "actionKey": "",
                                  "at": self.q.time.time()}],
                     "reserved": {"1": self.q.time.time()},
                     "reservedThreads": {"1": "launch:mcp:launch:new"}})
        args = argparse.Namespace(
            args=json.dumps({"projectId": "fixture", "title": TITLE, "message": "fix",
                             "taskType": "standard",
                             "clientRequestId": request}),
            title=None, priority=800, tool="t3_thread_launch", action_key=None)
        with patch.object(self.q, "active_thread_ids", return_value=set()), \
                patch.object(self.q, "read_rules", return_value="rules"), \
                redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as refused:
                self.q.cmd_start(args)
        self.assertEqual(refused.exception.code, 1)
        self.assertEqual(self.q.load()["items"], [])

    def test_a_message_a_later_one_replaced_is_real_work_again(self):
        # The finding: A finishes, B starts on the same thread, so the thread is
        # live again. Asking for A again is real work, not a copy of B.
        now = self.q.time.time()
        self.q.save({"next": 3, "items": [], "started": [
            {"id": 1, "title": TITLE, "target": THREAD, "thread": THREAD,
             "actionKey": "", "at": now - 60},
            {"id": 2, "title": "MO#544 check", "target": THREAD, "thread": THREAD,
             "actionKey": "", "at": now}]})
        with patch.object(self.q, "active_thread_ids", return_value={THREAD}):
            code, err = self.start()
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.q.load()["items"]), 1)

    def test_the_latest_message_on_a_live_thread_is_still_refused(self):
        # The same sequence asked the other way round: the message the thread
        # is working now is still a duplicate.
        now = self.q.time.time()
        self.q.save({"next": 3, "items": [], "started": [
            {"id": 1, "title": TITLE, "target": THREAD, "thread": THREAD,
             "actionKey": "", "at": now - 60},
            {"id": 2, "title": "MO#544 check", "target": THREAD, "thread": THREAD,
             "actionKey": "", "at": now}]})
        with patch.object(self.q, "active_thread_ids", return_value={THREAD}):
            code, err = self.start(title="MO#544 check")
        self.assertEqual(code, 1)
        self.assertIn("already started as coordq #2", err)

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
                             "taskType": "standard",
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
                           "taskType": "standard"})

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


class WakeMetricsTests(unittest.TestCase):
    def test_wake_metrics_report_from_the_inbox_and_the_journal(self):
        sys.path.insert(0, str(ROOT / "coordinator/bin"))
        self.addCleanup(sys.path.remove, str(ROOT / "coordinator/bin"))
        import inbox as store

        base = dict(source="journal", ts=1.0)
        metrics = tempfile.mkdtemp(prefix="selftest-metrics-")
        with patch.dict(os.environ, {"COORD_INBOX_DIR": metrics}):
            store.enqueue("pr_opened", "pr_opened:a#5", repo="shyamsivakumar/mac-ops", pr=5, **base)
            store.enqueue("pr_opened", "pr_opened:b#6", repo="other/repo", pr=6, **base)
            store.enqueue("recut", "recut:5", pr=5, **base)
            rows = store.claim("coordinator", worker="m", now=2.0, pid=os.getpid())
            store.ack(rows[:1], now=3.0)
            conn = store.connect()
            conn.execute("INSERT INTO outbox(ts, run_id, kind, sent_ts) VALUES (1.0, ?, 'send', 601.0)", (rows[0]["run_id"],))
            conn.close()
        github = os.path.join(metrics, "prs.json")
        json.dump([{"number": 5, "createdAt": "2026-11-23T15:00:00Z"}, {"number": 6, "createdAt": "2026-11-23T15:00:00Z"}], open(github, "w"))
        many = os.path.join(metrics, "many.json")
        json.dump([{"number": n, "createdAt": "2026-11-23T15:00:00Z"} for n in range(1000)], open(many, "w"))
        fixtures = ROOT / "evidence/event-inbox-design/tickets/fixtures"
        spec = importlib.util.spec_from_file_location("coord_wake_metrics", ROOT / "scripts/coord_wake_metrics.py")
        wake_metrics = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wake_metrics)
        reports = []
        for prs in (github, many):
            out = io.StringIO()
            with patch.dict(os.environ, {"HOME": "/nonexistent"}), contextlib.redirect_stdout(out):
                wake_metrics.main(["--json", "--inbox-dir", metrics, "--github-prs", prs,
                                   "--journal", str(fixtures / "journal-sample.jsonl"), "--launcher-log", str(fixtures / "launcher-sample.log")])
            reports.append(json.loads(out.getvalue()))
        report, capped = reports
        self.assertEqual((report["buckets"]["skipped"], report["buckets"]["lock_skipped"]), (1, 1))
        self.assertEqual((capped["lost"]["never_enqueued"], capped["lost"]["never_enqueued_truncated"]), (None, True))
        self.assertEqual((report["runs"], report["duplicate_rate"]["journal"]), (6, 0.333))
        self.assertEqual((report["volume"]["inbox"], report["latency"]["inbox_min"]["batch"]["median"]), ({"pr_opened/batch": 2, "recut/wake": 1}, 10.0))
        self.assertEqual((report["lost"]["stuck"], report["lost"]["never_enqueued"]), (2, [6]))
        self.assertEqual(sqlite3.connect(os.path.join(metrics, "inbox.db")).execute("SELECT COUNT(*) FROM inbox").fetchone()[0], 3)
        conn = sqlite3.connect(os.path.join(metrics, "inbox.db"))
        conn.execute("INSERT INTO inbox(ts, kind, status, repo, pr, tier, done_ts) VALUES (1795459920.0, 'pr_review', 'pending', 'shyamsivakumar/mac-ops', 7, 'batch', NULL), (1795459920.0, 'pr_review', 'done', 'shyamsivakumar/mac-ops', 8, 'batch', 1795470000.0)")
        conn.commit()
        conn.close()
        out = io.StringIO()
        with patch.dict(os.environ, {"HOME": "/nonexistent"}), contextlib.redirect_stdout(out):
            wake_metrics.main(["--json", "--inbox-dir", metrics, "--since", "2026-11-23T15:40:00Z",
                               "--until", "2026-11-23T21:06:00Z", "--journal", str(fixtures / "journal-sample.jsonl"),
                               "--launcher-log", str(fixtures / "launcher-sample.log")])
        self.assertEqual(json.loads(out.getvalue())["lost"]["stuck"], 2)


if __name__ == "__main__":
    unittest.main()
