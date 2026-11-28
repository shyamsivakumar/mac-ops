import argparse
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
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
        self.q.active_thread_ids = lambda: set()
        self.q.review_max = lambda: 3
        self.q.save({"next": 2, "items": [
            {"id": 1, "tool": "t3_thread_launch", "args": {},
             "priority": 0, "title": "queued"}]})

    def refill(self):
        candidates = self.q.Candidates([{"repository": {"nameWithOwner": "o/r"},
                                         "number": n, "title": str(n)} for n in range(10)], [], (), {}, {"o/r": 10})
        with patch.object(self.q, "board_candidates", return_value=candidates), patch.object(
                self.q, "ticket_start", return_value=(0, "started")) as start:
            self.q.refill(argparse.Namespace(dry_run=False))
            return start.call_count

    def test_nonempty_queue_fills_only_two_slots_with_lagging_count(self):
        self.assertEqual(self.refill(), 2)

    def refill_starts(self, candidates, live):
        self.q.save({"next": 1, "items": []})
        self.q.live = lambda: live
        with patch.object(self.q, "board_candidates", return_value=candidates), patch.object(
                self.q, "ticket_start", return_value=(0, "started")) as start, patch.object(
                self.q, "last_refill", return_value=None):
            self.q.refill(argparse.Namespace(dry_run=False))
        return [call.args[:2] for call in start.call_args_list]

    def test_lanes_max_fills_idle_slots(self):
        self.q.cap = lambda: 9
        todo = [{"repository": {"nameWithOwner": "o/s"}, "number": n, "title": str(n)} for n in range(24)]
        active = {"o/s": {"a", "b", "c"}}
        floor = self.q.Candidates(todo, [], (), active, {"o/s": 3})
        self.assertEqual(self.refill_starts(floor, 3), [])
        ceiling = self.q.Candidates(todo, [], (), active, {"o/s": 3}, {"o/s": 5})
        self.assertEqual(len(self.refill_starts(ceiling, 3)), 2)

    def test_no_repo_starves(self):
        label = [{"name": "stage:todo"}]
        rows = [{"repository": {"nameWithOwner": repo}, "number": n, "title": str(n), "labels": label}
                for repo, count in (("o/s", 24), ("o/a", 1)) for n in range(1, count + 1)]
        candidates = self.q.lane_candidates(rows, set(), {}, (), {}, {"o/s": 3, "o/a": 1}, {"o/s": 5})
        self.assertEqual(sorted({repo for repo, _ in self.refill_starts(candidates, 3)}), ["o/a", "o/s"])

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

    def queue_burst(self, key=lambda n: f"ticket:o/r#{n}:a1"):
        self.q.save({"next": 31, "items": [
            {"id": n, "tool": "t3_thread_launch", "args": {"clientRequestId": key(n)},
             "priority": 0, "title": "burst"} for n in range(1, 31)]})
        self.q.live = lambda: 0

    def test_burst_with_stale_total_and_individual_visibility(self):
        self.queue_burst()
        visible = set()
        started = []
        def start(tool, args, rules=None):
            started.append(f"t{len(started) + 1}")
            self.assertLessEqual(len(visible) + len(self.q.load()["reserved"]), 5)
            return 0, json.dumps({"threadId": started[-1]})
        with patch.object(self.q, "active_thread_ids", side_effect=lambda: set(visible)), patch.object(
                self.q, "thread_status", return_value="running"), patch.object(self.q, "call", side_effect=start):
            self.q.drain()
            self.assertEqual(len(started), 5)
            for thread in started[:]:
                visible.add(thread)
                self.q.drain()
                self.assertEqual(len(started), 5)
                self.assertEqual(len(visible) + len(self.q.load()["reserved"]), 5)

    def test_expired_reservation_does_not_block(self):
        self.queue_burst()
        data = self.q.load()
        data["reserved"] = {"old": self.q.time.time() - 601}
        self.q.save(data)
        with patch.object(self.q, "active_thread_ids", return_value=set()), patch.object(
                self.q, "thread_status", return_value="running"), patch.object(
                self.q, "call", return_value=(0, json.dumps({"threadId": "t"}))) as start:
            self.q.drain()
        self.assertEqual(start.call_count, 5)
        self.assertNotIn("old", self.q.load()["reserved"])

    def test_sends_hold_no_slot(self):
        self.queue_sends()
        with patch.object(self.q, "active_thread_ids", return_value={str(n) for n in range(6)}), patch.object(
                self.q, "call", return_value=(0, "{}")) as start:
            self.q.live = lambda: 6
            self.q.drain()
        self.assertEqual(start.call_count, 30)

    def run_drain(self, live_builds=0, reviews=()):
        threads = {f"b{n}" for n in range(live_builds)} | {f"r{n}" for n in range(len(reviews))}
        Path(self.tmp.name, "dispatch-receipts.json").write_text(json.dumps({f"gate:o/r#{n}:{'a' * 40}": f"r{n}" for n in range(len(reviews))}))
        self.q.live = lambda: len(threads)
        started = []
        def start(tool, args, rules=None):
            started.append(args["clientRequestId"])
            self.assertLessEqual(len(threads) + len(self.q.load()["reserved"]), 6)
            return 0, json.dumps({"threadId": f"new{len(started)}"})
        with patch.object(self.q, "active_thread_ids", return_value=threads), patch.object(
                self.q, "thread_status", return_value="running"), patch.object(self.q, "call", side_effect=start):
            self.q.drain()
        return started

    def test_reviews_do_not_starve_builds(self):
        self.queue_burst(lambda n: f"gate:o/r#{n}:{'a' * 40}" if n <= 10 else f"ticket:o/r#{n}:a1")
        data = self.q.load()
        for item in data["items"]:
            item["priority"] = 5000 if item["args"]["clientRequestId"].startswith("gate:") else 0
        data["items"] = data["items"][:15]
        self.q.save(data)
        started = self.run_drain()
        self.assertEqual(len([k for k in started if k.startswith("gate:")]), 3)
        self.assertEqual(len([k for k in started if k.startswith("ticket:")]), 3)

    def test_builds_do_not_starve_reviews(self):
        self.queue_burst(lambda n: "ticket:o/r#1:a1" if n > 1 else f"gate:o/r#1:{'a' * 40}")
        data = self.q.load()
        data["items"] = [{**item, "priority": 0 if item["id"] == 1 else 100} for item in data["items"][:3]]
        self.q.save(data)
        started = self.run_drain(live_builds=5)
        self.assertEqual(started, [f"gate:o/r#1:{'a' * 40}"])

    def test_no_head_of_line_block(self):
        pre = {"tool": "t3_thread_launch", "args": {"clientRequestId": "ticket:o/r#9:a1"}}
        self.q.save({"next": 3, "items": [
            {"id": 1, "tool": "t3_thread_launch", "args": {"clientRequestId": "ticket:o/r#1:a1"}, "pre": [pre], "priority": 9, "title": "two"},
            {"id": 2, "tool": "t3_thread_launch", "args": {"clientRequestId": "ticket:o/r#2:a1"}, "priority": 0, "title": "one"}]})
        started = self.run_drain(live_builds=4, reviews=(1,))
        self.assertEqual(started, ["ticket:o/r#2:a1"])

    def test_failed_start_releases_reservation(self):
        self.queue_sends()
        data = self.q.load()
        data["items"] = data["items"][:1]
        self.q.save(data)
        with patch.object(self.q, "active_thread_ids", return_value=set()), patch.object(self.q, "call", return_value=(1, "failed")):
            self.q.drain()
        self.assertEqual(self.q.load()["reserved"], {})

    def test_a_timeout_three_minutes_old_releases_a_slot_nobody_uses(self):
        # A launch whose thread never shows live still comes back: the slot
        # it holds is not held for ten minutes.
        self.queue_sends()
        data = self.q.load()
        data["items"] = data["items"][:1]
        data["reserved"] = {"stale": self.q.time.time() - 181}
        data["reservedThreads"] = {"stale": "mcp:launch:gone"}
        self.q.save(data)
        with patch.object(self.q, "active_thread_ids", return_value=set()), patch.object(
                self.q, "thread_status", return_value="running"), patch.object(
                self.q, "call", return_value=(0, "{}")):
            self.q.drain()
        self.assertNotIn("stale", self.q.load()["reserved"])

    def test_status_reconciles_under_the_writer_lock_the_start_takes(self):
        # A start can enqueue between a read and a write, so a write of an
        # older snapshot would drop the item it just queued. The read, the
        # reconciliation and the write all happen under the writer lock.
        self.q.save({"next": 2, "items": [],
                     "reserved": {"7": self.q.time.time()},
                     "reservedThreads": {"7": "launch:mcp:launch:one"}})
        real_lock, real_save, held, saves, reads = (self.q.Lock, self.q.save, [], [], [])

        class Recording(real_lock):
            def __enter__(self):
                held.append("enter")
                return super().__enter__()

            def __exit__(self, *exc):
                held.append("exit")
                return super().__exit__(*exc)

        def save(queue):
            saves.append(list(held))
            return real_save(queue)

        def live_ids():
            reads.append(list(held))
            return set()

        with patch.object(self.q, "Lock", Recording), patch.object(self.q, "save", side_effect=save), \
                patch.object(self.q, "active_thread_ids", side_effect=live_ids), \
                patch.object(self.q, "thread_status", return_value="completed"), \
                patch.object(self.q, "load_counts", return_value={}), \
                redirect_stdout(io.StringIO()) as out:
            self.q.cmd_status(None)
        # The released reservation was written while the lock was held.
        self.assertEqual(saves, [["enter"]])
        # The thread list was read before the lock, so a t3 call never blocks
        # a start.
        self.assertEqual(reads, [[]])
        self.assertEqual(json.loads(out.getvalue())["reserved"], {})

    def test_a_reservation_taken_after_the_thread_read_is_left_alone(self):
        # The finding: the thread list says T is live, T finishes, and a new
        # send reserves T before the writer lock is taken. That reservation is
        # not the one the list was read for, so it keeps its slot and the cap
        # cannot be crossed.
        now = self.q.time.time()
        queue = {"next": 2, "items": [],
                 "reserved": {"new": now},
                 "reservedThreads": {"new": "mcp:launch:t"}}
        with patch.object(self.q, "save"):
            self.q.reconcile_reservations(queue, {"mcp:launch:t"}, {}, snapshot={})
        self.assertIn("new", queue["reserved"])

    def test_a_reservation_the_snapshot_holds_is_still_released(self):
        now = self.q.time.time()
        queue = {"next": 2, "items": [],
                 "reserved": {"7": now},
                 "reservedThreads": {"7": "mcp:launch:t"}}
        snapshot = {"7": {"at": now, "thread": "mcp:launch:t"}}
        with patch.object(self.q, "save"):
            self.q.reconcile_reservations(queue, {"mcp:launch:t"}, {}, snapshot)
        self.assertEqual(queue["reserved"], {})

    def test_a_snapshot_reconciliation_never_looks_a_status_up(self):
        # The second finding: the statuses are read before the writer lock, so
        # a reconciliation that has a snapshot never calls t3 itself. A launch
        # the read did not cover keeps its slot instead.
        now = self.q.time.time()
        queue = {"next": 2, "items": [],
                 "reserved": {"7": now},
                 "reservedThreads": {"7": "launch:mcp:launch:one"}}
        snapshot = {"7": {"at": now, "thread": "launch:mcp:launch:one"}}
        with patch.object(self.q, "thread_status") as status, patch.object(self.q, "save") as save:
            self.q.reconcile_reservations(queue, set(), {}, snapshot)
        status.assert_not_called()
        save.assert_not_called()
        self.assertIn("7", queue["reserved"])

    def test_status_reads_launch_statuses_before_taking_the_writer_lock(self):
        # The second finding: a status lookup under the lock would block every
        # queue writer for its length.
        self.q.save({"next": 2, "items": [],
                     "reserved": {"7": self.q.time.time()},
                     "reservedThreads": {"7": "launch:mcp:launch:one"}})
        real_lock, held, lookups = self.q.Lock, [], []

        class Recording(real_lock):
            def __enter__(self):
                held.append("enter")
                return super().__enter__()

            def __exit__(self, *exc):
                held.append("exit")
                return super().__exit__(*exc)

        def status(thread):
            lookups.append(list(held))
            return "completed"

        with patch.object(self.q, "Lock", Recording), \
                patch.object(self.q, "active_thread_ids", return_value=set()), \
                patch.object(self.q, "thread_status", side_effect=status), \
                patch.object(self.q, "load_counts", return_value={}), \
                redirect_stdout(io.StringIO()) as out:
            self.q.cmd_status(None)
        # The lookup happened with no lock held, and its answer released the
        # slot inside the lock.
        self.assertEqual(lookups, [[]])
        self.assertEqual(json.loads(out.getvalue())["reserved"], {})
        self.assertEqual(self.q.load()["reserved"], {})

    def test_status_reconciles_a_reservation_its_launch_no_longer_needs(self):
        # The reported reserved set is what the queue holds now, so a read
        # does not show a slot that no thread uses.
        self.q.save({"next": 2, "items": [],
                     "reserved": {"7": self.q.time.time()},
                     "reservedThreads": {"7": "launch:mcp:launch:one"}})
        out = io.StringIO()
        with patch.object(self.q, "active_thread_ids", return_value=set()), patch.object(
                self.q, "thread_status", return_value="completed"), patch.object(
                self.q, "load_counts", return_value={}), redirect_stdout(out):
            self.q.cmd_status(None)
        self.assertEqual(json.loads(out.getvalue())["reserved"], {})
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
        # Elapsed time alone must not free the slot inside the timeout: only a
        # terminal status does. The timeout is three minutes.
        self.q.save({"next": 2, "items": [],
                     "reserved": {"7": self.q.time.time() - 120},
                     "reservedThreads": {"7": "launch:mcp:launch:one"}})
        self.q.live = lambda: 0
        with patch.object(self.q, "active_thread_ids", return_value=set()), patch.object(
                self.q, "thread_status", return_value="waiting"):
            self.q.drain()
        self.assertIn("7", self.q.load()["reserved"])

    def test_a_start_reads_the_thread_list_before_taking_the_writer_lock(self):
        # The finding: a slow thread-list read while holding the writer lock
        # holds every other start. The read happens first, and the records it
        # speaks for are snapshotted, so a record written since counts as
        # running.
        self.q.save({"next": 2, "items": [],
                     "started": [{"id": 1, "title": "older", "target": "other",
                                  "thread": "other", "actionKey": "",
                                  "at": self.q.time.time()}]})
        real_lock, held, reads = self.q.Lock, [], []

        class Recording(real_lock):
            def __enter__(self):
                held.append("enter")
                return super().__enter__()

            def __exit__(self, *exc):
                held.append("exit")
                return super().__exit__(*exc)

        def live_ids():
            reads.append(list(held))
            return {"other"}

        args = argparse.Namespace(
            args=json.dumps({"threadId": "mcp:launch:builder", "message": "fix"}),
            title="MO#544 gate findings", priority=800, tool="t3_thread_send",
            action_key=None)
        with patch.object(self.q, "Lock", Recording), \
                patch.object(self.q, "active_thread_ids", side_effect=live_ids), \
                patch.object(self.q, "drain"), redirect_stderr(io.StringIO()), \
                redirect_stdout(io.StringIO()):
            try:
                self.q.cmd_start(args)
            except SystemExit as e:
                self.assertEqual(e.code, 0)
        # The dedupe read is the first one and it runs with no lock held. The
        # dispatch after it (drain) is stubbed, since a send holds no slot.
        self.assertEqual(reads[0], [])
        self.assertIn("enter", held)

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
        self.assertEqual(len(calls), 5)

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


class QueueCrashSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.q = load_coordq()
        self.q.DIR = self.tmp.name
        env = patch.dict(os.environ, {"COORD_JOURNAL_DIR": self.tmp.name + "/j"})
        env.start()
        self.addCleanup(env.stop)
        self.q.DECISIONS_PATH = self.tmp.name + "/decisions.json"
        Path(self.q.DECISIONS_PATH).write_text(json.dumps({"items": []}))

    def test_a_corrupt_queue_with_no_prev_stops_dispatch_and_returns_empty(self):
        Path(self.tmp.name, "queue.json").write_text('{"next":1,"items":[')
        self.assertEqual(self.q.load(), {"next": 1, "items": []})
        self.assertTrue(Path(self.tmp.name, "dispatch.stopped").exists())
        journal = "".join(
            p.read_text() for p in Path(self.tmp.name, "j").iterdir())
        self.assertIn("queue.json invalid and no queue.json.prev", journal)

    def test_a_fallback_raises_one_board_item_once(self):
        Path(self.tmp.name, "queue.json").write_text('{"next":1,"items":[')
        Path(self.tmp.name, "queue.json.prev").write_text('{"next":5,"items":[]}')
        self.q.load()
        self.q.load()
        board = json.loads(Path(self.q.DECISIONS_PATH).read_text())
        items = [e for e in board["items"]
                 if isinstance(e, dict) and e.get("id") == "factory-dispatch-stopped"]
        self.assertEqual(len(items), 1)
        self.assertIn("rm dispatch.stopped", items[0]["why"])

    def test_a_truncated_queue_falls_back_and_stops_dispatch(self):
        Path(self.tmp.name, "queue.json").write_text('{"next":1,"items":[')
        Path(self.tmp.name, "queue.json.prev").write_text('{"next":5,"items":[]}')
        self.assertEqual(self.q.load()["next"], 5)
        self.assertTrue(Path(self.tmp.name, "dispatch.stopped").exists())

    def test_dispatch_and_refill_refuse_while_stopped(self):
        Path(self.tmp.name, "dispatch.stopped").write_text("")
        with patch.object(self.q, "drain") as drain, patch.object(
                self.q, "board_candidates") as candidates:
            self.q.cmd_dispatch(argparse.Namespace(dry_run=False))
            self.q.refill(argparse.Namespace(dry_run=False))
        drain.assert_not_called()
        candidates.assert_not_called()

    def test_save_keeps_the_previous_queue(self):
        self.q.save({"next": 1, "items": []})
        self.q.save({"next": 2, "items": []})
        prev = json.loads(Path(self.tmp.name, "queue.json.prev").read_text())
        self.assertEqual(prev["next"], 1)

    def test_first_dispatch_after_corruption_dispatches_nothing(self):
        self.q.live = lambda: 0
        self.q.cap = lambda: 6
        Path(self.tmp.name, "queue.json").write_text('{"next":2,"items":[')
        Path(self.tmp.name, "queue.json.prev").write_text(json.dumps({"next": 2, "items": [
            {"id": 1, "tool": "t3_thread_send", "args": {"threadId": "1"},
             "priority": 0, "title": "pending"}]}))
        with patch.object(self.q, "call", return_value=(0, "{}")) as call, patch.object(
                self.q, "active_thread_ids", return_value=set()), patch.object(
                self.q, "flush_provider_blocks"), patch.object(self.q, "safe_refill"):
            self.q.cmd_dispatch(argparse.Namespace(dry_run=False))
        call.assert_not_called()
        self.assertTrue(Path(self.tmp.name, "dispatch.stopped").exists())
