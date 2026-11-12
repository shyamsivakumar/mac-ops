"""MO-181: temporary homes and extracted functions only; never run a hub."""
import contextlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_hub_install as base


class BatchInstallTests(unittest.TestCase):
    def setUp(self):
        self.fixture = base.IdleInstallTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.home = self.fixture.home

    def gate(self, source):
        namespace = {"HUB_DIR": str(self.home / ".empryo-hub"),
                     "json": json, "os": os, "time": time}
        return base.functions(base.ROOT / "empryo/bin" / source,
                              {"install_pending"}, namespace)["install_pending"]

    def test_five_minutes_starts_a_turn_but_31_minutes_keeps_work_queued(self):
        started = []
        runtime = {}
        thread = {"threadId": "fake", "status": "idle", "runCount": 0, "runs": []}
        hub = {"runtime_of": lambda tid: runtime, "require_unheld": lambda t: None,
               "LOCK": threading.RLock(), "HubError": RuntimeError,
               "LIVE": ("running", "waiting", "queued"), "DRAINING": {"requested": False},
               "install_pending": self.gate("emp-hub"), "log": lambda msg: None,
               "set_status": lambda t, status: t.update(status=status),
               "choose_model": lambda t: ("fake", False), "ensure_session": lambda t, m: object(),
               "now_iso": lambda: "fake", "append_item": lambda *args: None,
               "run_turn": lambda *args: None,
               "threading": SimpleNamespace(Thread=lambda **kwargs: SimpleNamespace(start=lambda: started.append(kwargs)))}
        start = base.functions(base.ROOT / "empryo/bin/emp-hub", {"start_turn"}, hub)["start_turn"]
        queue = {"items": [{"id": 1, "priority": 0, "tool": "emp_thread_launch", "args": {}, "title": "fake"}]}
        namespace = {"install_pending": self.gate("empq"), "log": lambda msg: None,
                     "load": lambda: queue, "save": lambda q: None,
                     "MAX_ATTEMPTS": 3, "live": lambda: 0, "cap": lambda: 1,
                     "call": lambda *args: (0, start(thread, "work")),
                     "wait_until_counted": lambda before: None}
        drain = base.functions(base.ROOT / "empryo/bin/empq", {"drain"}, namespace)["drain"]
        with patch("os.path.expanduser", return_value=str(base.WORKER.state_path(self.home))):
            with patch("time.time", return_value=400):
                drain()
                self.assertEqual(thread["status"], "running")
                self.assertEqual(len(started), 1)
                self.assertFalse(queue["items"])
            queue["items"] = [{"id": 2, "priority": 0}]
            with patch("time.time", return_value=1960):
                drain()
                self.assertEqual(queue["items"][0]["id"], 2)
                self.assertEqual(len(started), 1)

    def test_gates_agree_at_boundary_and_fail_closed_on_invalid_time(self):
        for source in ("empq", "emp-hub"):
            gate = self.gate(source)
            with patch("os.path.expanduser", return_value=str(base.WORKER.state_path(self.home))):
                for state in ("pending", "waiting idle"):
                    base.WORKER.save(self.home, {"state": state, "since": 100})
                    for now, expected in ((400, False), (1899, False), (1900, True), (1960, True)):
                        with patch("time.time", return_value=now):
                            self.assertEqual(gate(), expected, (source, state, now))
                for state in ("installing", "restarting"):
                    base.WORKER.save(self.home, {"state": state, "since": 100})
                    with patch("time.time", return_value=400):
                        self.assertTrue(gate())
                for since in (None, "100", True, float("nan"), float("inf"), 500):
                    base.WORKER.save(self.home, {"state": "pending", "since": since})
                    with patch("time.time", return_value=400):
                        self.assertTrue(gate(), (source, since))

    def test_merges_during_window_coalesce_then_install_restart_once(self):
        f = self.fixture
        self.assertEqual(f.tick(now=400)["state"], "pending")
        self.assertFalse(f.calls)
        path = f.checkout / "empryo/hub/routing.json"
        path.write_text(path.read_text() + "\n")
        f.git("commit", "-am", "second managed merge", "-q")
        latest = f.git("rev-parse", "HEAD")
        merge_ns = {"contextlib": contextlib, "threading": threading, "LOCK": threading.RLock(),
                    "LIVE": ("running", "waiting", "queued"), "HubError": RuntimeError,
                    "runtime_of": lambda tid: {}, "install_pending": self.gate("emp-hub")}
        merge = base.functions(base.ROOT / "empryo/bin/emp-hub", {"merge_guard"}, merge_ns)["merge_guard"]
        with patch("time.time", return_value=500):
            with merge({"threadId": "merge", "status": "completed"}):
                base.WORKER.mark(f.checkout, self.home, f.sha, latest)
        self.assertEqual(base.WORKER.read_state(self.home)["sha"], latest)
        self.assertEqual(base.WORKER.read_state(self.home)["since"], 100)
        for args in (("fetch", "origin"), ("merge", "--ff-only", "origin/main")):
            subprocess.run(["git", "-C", str(f.install), *args], check=True, capture_output=True)
        self.assertEqual(f.tick(now=1960)["state"], "done")
        self.assertEqual(f.tick(now=1961)["state"], "done")
        self.assertEqual(len(f.calls), 2)
        self.assertFalse(f.notices)

    def test_running_turn_after_wait_still_prevents_all_side_effects(self):
        f = self.fixture
        f.idle = False
        self.assertEqual(f.tick(now=1960)["state"], "waiting idle")
        self.assertFalse(f.calls)
        f.idle = True
        self.assertEqual(f.tick(now=1961)["state"], "done")
        self.assertEqual(len(f.calls), 2)

    def test_non_main_checkout_refuses_after_wait(self):
        f = self.fixture
        subprocess.run(["git", "-C", str(f.install), "checkout", "-b", "other"], check=True, capture_output=True)
        self.assertEqual(f.tick(now=1960)["state"], "refused")
        self.assertFalse(f.calls)

    def test_origin_main_mismatch_refuses_after_wait(self):
        f = self.fixture
        original = base.WORKER.git
        def git(checkout, *args):
            return "0" * 40 if args == ("rev-parse", "origin/main") else original(checkout, *args)
        with patch.object(base.WORKER, "git", side_effect=git):
            self.assertEqual(f.tick(now=1960)["state"], "refused")
        self.assertFalse(f.calls)

    def test_missing_hub_identity_refuses_after_wait(self):
        f = self.fixture
        report = lambda home: {"installPending": True, "installIdle": True, "pid": None}
        self.assertEqual(f.tick(now=1960, status=report)["state"], "refused")
        self.assertFalse(f.calls)


if __name__ == "__main__":
    unittest.main()
