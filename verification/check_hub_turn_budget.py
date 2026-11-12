#!/usr/bin/env python3
"""Isolated second-socket proof, real sleep processes, simulated elapsed time.

Only ACP/provider and GitHub I/O are faked. No production stores, engines,
sockets, threads, installed binaries, or pull requests are touched.
"""
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_hub(home):
    loader = SourceFileLoader("disposable_hub", str(ROOT / "empryo/bin/emp-hub"))
    hub = types.ModuleType(loader.name)
    with patch.dict(os.environ, {"HOME": str(home)}):
        loader.exec_module(hub)
    return hub


class Clock:
    def __init__(self):
        self.offset = 0

    def time(self):
        return time.time() + self.offset

    def __getattr__(self, key):
        return getattr(time, key)


class SleepEngine:
    def __init__(self, hub, thread):
        self.hub, self.thread = hub, thread
        self.users, self.last_used, self.dead = 1, time.time(), False
        self.started = threading.Event()
        self.proc = None
        self.cancels = 0
        self.answers = []
        self.block_answer = False
        self.answer_started = threading.Event()
        self.answer_finish = threading.Event()

    def call(self, method, params, timeout=None):
        assert method == "session/prompt"
        self.proc = subprocess.Popen(["/bin/sleep", "3600"])
        self.started.set()
        self.proc.wait()
        return {"stopReason": "cancelled" if self.cancels else "end_turn"}

    def notify(self, method, params):
        assert method == "session/cancel"
        self.cancels += 1
        self.proc.terminate()

    def send(self, message):
        if self.block_answer:
            self.answer_started.set()
            assert self.answer_finish.wait(5)
        self.answers.append(message)

    def close(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait()


class TurnBudgetProof(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hb-", dir="/tmp")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.engines = []
        self.timers = []
        self.boot()
        self.addCleanup(self.stop)

    def boot(self):
        h = self.hub = load_hub(self.home)
        for directory in (h.HUB_DIR, h.TRANSCRIPTS, h.WORKTREES):
            Path(directory).mkdir(parents=True, exist_ok=True)
        routing = json.loads((ROOT / "empryo/hub/routing.json").read_text())
        Path(h.ROUTING_PATH).write_text(json.dumps(routing))
        h.time = self.clock = Clock()
        h.resolve_caller = lambda: None
        h.flush_titles = lambda: None
        h.auto_link_pull_requests = lambda t: []
        h.PROJECTS.data["proof"] = h.new_project("proof", "disposable", str(self.home))
        h.PROJECTS.save()
        self.releases = []
        release = h.release_engine

        def release_engine(proc):
            self.releases.append(proc.thread["threadId"])
            release(proc)

        def ensure(thread, model=None):
            proc = SleepEngine(h, thread)
            self.engines.append(proc)
            thread["sessionId"] = thread["threadId"]
            thread["sessionDir"] = str(self.home / "fake-session")
            h.SESSION_THREAD[thread["sessionId"]] = thread["threadId"]
            h.runtime_of(thread["threadId"])["proc"] = proc
            return proc

        real_timer = threading.Timer

        def timer(*args, **kwargs):
            obj = real_timer(*args, **kwargs)
            obj.daemon = True
            self.timers.append(obj)
            return obj

        h.release_engine = release_engine
        h.ensure_session = ensure
        h.threading = types.SimpleNamespace(**{k: getattr(threading, k) for k in dir(threading) if not k.startswith("__")})
        h.threading.Timer = timer
        self.exited = threading.Event()
        h.os = types.SimpleNamespace(**{k: getattr(os, k) for k in dir(os) if not k.startswith("__")})
        h.os._exit = lambda code: self.exited.set()
        self.server = h.Server(h.SOCKET, h.Handler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        print(f"SECOND HUB socket={h.SOCKET}; synthetic clock; no production access")

    def stop(self):
        for timer in self.timers:
            timer.cancel()
        for engine in self.engines:
            engine.close()
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server_thread.join()
            self.server = None
        for t in list(self.hub.THREADS.data.values()):
            if t.get("activeRunId"):
                self.until(lambda: not t["activeRunId"])

    def rpc(self, tool, **arguments):
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(5)
            s.connect(self.hub.SOCKET)
            s.sendall((json.dumps({"method": "call", "tool": tool, "arguments": arguments}) + "\n").encode())
            with s.makefile() as stream:
                response = json.loads(stream.readline())
        if not response["ok"]:
            raise self.hub.HubError(response["error"])
        return response["result"]

    def until(self, condition):
        deadline = time.monotonic() + 5
        while not condition():
            if time.monotonic() > deadline:
                self.fail("disposable hub did not settle")
            threading.Event().wait(0.005)

    def launch(self, title="MO-147 proof", **kwargs):
        result = self.rpc("emp_thread_launch", projectId="proof", title=title, message="sleep", modelSelection={"instanceId": "empryo", "model": "subscriptions/claude-opus-5-5"}, **kwargs)
        return self.hub.THREADS.data[result["threadId"]]

    def wait_started(self, thread):
        # A resumed turn is started by a background thread, so the engine can
        # still be missing a moment after the call that queued it returns.
        deadline = time.monotonic() + 5
        while True:
            proc = self.hub.runtime_of(thread["threadId"])["proc"]
            if proc is not None:
                break
            if time.monotonic() > deadline:
                self.fail("the turn did not start")
            threading.Event().wait(0.005)
        self.assertTrue(proc.started.wait(5))
        return proc

    def expire(self, thread):
        self.hub.stall_check()
        self.hub.stall_check()
        self.until(lambda: not thread["activeRunId"])
        self.until(lambda: self.hub.runtime_of(thread["threadId"])["proc"].users == 0)
        return thread["runs"][-1]

    def test_total_budget_precedes_tool_and_progress_limits(self):
        h = self.hub
        rt = h.runtime_of("disposable")
        rt.update(turnStartedAt=1000, progressAt=1600, tools={"sleep": {"since": 1000}})
        limits = {"turnSeconds": 600, "toolSeconds": 10800, "noProgressSeconds": 1200}
        self.assertEqual(h.stall_reason(rt, limits, 1600), None)
        self.assertEqual(h.stall_reason(rt, limits, 1601), "turn budget exceeded: 10 min")
        rt["pending"]["question"] = {}
        self.assertIsNone(h.stall_reason(rt, limits, 2000))
        rt["pending"].clear()
        self.assertEqual(h.stall_reason(rt, limits, 2000), "turn budget exceeded: 10 min")

    def test_concurrent_provider_turns_and_resumed_clock(self):
        h = self.hub
        routing = json.loads(Path(h.ROUTING_PATH).read_text())
        self.assertNotIn("limits", routing)
        self.assertEqual(routing["turnLimits"], {"turnSeconds": 600, "noProgressSeconds": 1200, "toolSeconds": 10800, "taskTypeSeconds": {"standard": 600, "chore": 600, "ui": 600, "research": 600, "rca": 600, "risky": 600, "large": 600, "design": 600, "review": 1200}})
        self.assertEqual(h.turn_seconds_for(routing, "standard"), 600)
        self.assertEqual(h.turn_seconds_for(routing, "review"), 1200)
        first = self.launch(turnSeconds=600)
        first_proc = self.wait_started(first)
        second = self.launch(title="same provider, no queue", turnSeconds=600)
        second_proc = self.wait_started(second)
        self.assertEqual((first["status"], second["status"]), ("running", "running"))
        self.assertIsNone(first_proc.proc.poll())
        self.assertIsNone(second_proc.proc.poll())
        self.assertNotIn("limits", self.rpc("emp_hub_status"))
        for name in ("SLOTS", "limit_of", "acquire_slot", "release_slot"):
            self.assertFalse(hasattr(h, name), name)
        self.clock.offset += 601
        for thread, proc in ((first, first_proc), (second, second_proc)):
            record = self.expire(thread)
            self.assertEqual((record["status"], record["error"]), ("failed", "turn budget exceeded: 10 min"))
            self.assertEqual(proc.cancels, 1)
            self.assertEqual(self.releases.count(thread["threadId"]), 1)
        old_start = h.runtime_of(first["threadId"])["turnStartedAt"]
        self.rpc("emp_thread_send", threadId=first["threadId"], message="resume")
        resumed = self.wait_started(first)
        self.assertEqual(first["turnSeconds"], 600)
        self.assertGreater(h.runtime_of(first["threadId"])["turnStartedAt"], old_start)
        h.kill_if_still_active(h.runtime_of(first["threadId"]), resumed, old_start)
        self.assertIsNone(resumed.proc.poll(), "old grace timer killed a newer turn")
        self.clock.offset += 601
        self.expire(first)
        self.assertEqual(first["runCount"], 2)
        self.assertEqual(len(first["runs"]), 2)
        self.assertEqual(self.releases.count(first["threadId"]), 2)

    def test_drain_queue_does_not_charge_budget(self):
        h = self.hub
        h.DRAINING["requested"] = True
        thread = self.launch(turnSeconds=600)
        rt = h.runtime_of(thread["threadId"])
        self.assertEqual(thread["status"], "queued")
        self.assertEqual(rt["turnStartedAt"], 0)
        self.clock.offset += 601
        h.stall_check()
        self.assertFalse(rt["active"])
        self.assertIsNone(rt["stalled"])
        self.assertEqual(rt["turnStartedAt"], 0)
        self.rpc("emp_hub_drain_cancel")
        self.wait_started(thread)
        self.assertGreaterEqual(rt["turnStartedAt"], h.time.time() - 2)
        self.assertIsNone(rt["stalled"])
        self.clock.offset += 601
        self.assertEqual(self.expire(thread)["error"], "turn budget exceeded: 10 min")
        self.assertEqual(self.releases.count(thread["threadId"]), 1)

    def test_permission_answer_not_cut(self):
        h = self.hub
        thread = self.launch(turnSeconds=600)
        proc = self.wait_started(thread)
        h.handle_permission(proc, {"id": 9, "params": {"sessionId": thread["sessionId"], "_meta": {"empryo": {"category": "question"}}, "options": [{"kind": "allow_once", "name": "Yes", "optionId": "yes"}]}})
        self.clock.offset += 601
        h.stall_check()
        self.assertEqual(proc.cancels, 0)
        proc.block_answer = True
        results = []
        answer = threading.Thread(target=lambda: results.append(self.rpc("emp_thread_send", threadId=thread["threadId"], message="Yes")))
        answer.start()
        self.assertTrue(proc.answer_started.wait(5))
        h.stall_check()
        self.assertEqual(proc.cancels, 0, "cancelled in the middle of permission send")
        proc.answer_finish.set()
        answer.join(5)
        self.assertEqual(results[0]["delivery"], "answered")
        self.assertEqual(proc.answers[0]["result"]["outcome"]["optionId"], "yes")
        self.expire(thread)
        self.assertEqual(proc.cancels, 1)
        print("PERMISSION: deferred while pending and while answer send blocks; expiry after answer; wait time charged")

    def test_drain_reload_preserves_override(self):
        h = self.hub
        h.DRAINING["requested"] = True
        thread = self.launch(turnSeconds=9000)
        self.assertIn("pendingTurn", thread)
        self.assertEqual(thread["runCount"], 0)
        result = self.rpc("emp_hub_drain", timeoutMs=1000)
        self.assertTrue(result["drained"])
        self.assertTrue(self.exited.wait(5))
        tid = thread["threadId"]
        self.stop()
        Path(h.SOCKET).unlink()
        self.boot()
        h = self.hub
        h.resume_pending_turns()
        thread = h.THREADS.data[tid]
        self.wait_started(thread)
        self.assertEqual(thread["turnSeconds"], 9000)
        self.assertNotIn("pendingTurn", thread)
        rt = h.runtime_of(tid)
        rt["progressAt"] = h.time.time() + 8000
        self.clock.offset += 8000
        h.stall_check()
        self.assertIsNone(rt["stalled"])
        self.clock.offset += 1001
        record = self.expire(thread)
        self.assertEqual(record["error"], "turn budget exceeded: 150 min")
        print("DRAIN/RESTART: persisted 9000-second override; resume_turn applied it")

    def test_defaults_validation_and_extended_tool(self):
        h = self.hub
        for invalid in (599, True, "600", 600.5):
            with self.assertRaises(h.HubError):
                self.launch(turnSeconds=invalid)
        self.assertEqual(len(h.THREADS.data), 0)
        thread = self.launch()
        self.wait_started(thread)
        self.assertEqual(thread["turnSeconds"], 600)
        rt = h.runtime_of(thread["threadId"])
        rt["tools"]["sleep"] = {"since": h.time.time(), "status": "in_progress", "kind": "execute", "title": "sleep 3600"}
        self.clock.offset += 901
        self.assertEqual(self.expire(thread)["error"], "turn budget exceeded: 10 min")
        routing = json.loads(Path(h.ROUTING_PATH).read_text())
        routing["turnLimits"].pop("turnSeconds", None)
        Path(h.ROUTING_PATH).write_text(json.dumps(routing))
        legacy = self.launch()
        self.wait_started(legacy)
        self.assertEqual(legacy["turnSeconds"], 900)
        legacy.pop("turnSeconds")
        self.clock.offset += 901
        self.assertEqual(self.expire(legacy)["error"], "turn budget exceeded: 15 min")

    def test_merge_dry_run_provenance_after_fallback(self):
        h = self.hub
        task = self.launch()
        task_proc = self.wait_started(task)
        task_proc.proc.terminate()
        self.until(lambda: not task["activeRunId"])
        review = self.launch(title="MO-147 review", taskType="review")
        proc = self.wait_started(review)
        self.assertEqual(review["turnSeconds"], 1200)
        fallback = "subscriptions/gpt-6.1-terra"
        h.handle_update(review["sessionId"], {"sessionUpdate": "agent_message_chunk", "content": {"text": "Falling back to " + fallback}, "_meta": {"empryo": {"notice": True}}})
        h.handle_update(review["sessionId"], {"sessionUpdate": "agent_message_chunk", "content": {"text": "Checked all changes and the builder proof.\nVERDICT: PASS"}})
        proc.proc.terminate()
        self.until(lambda: not review["activeRunId"])
        sha = "a" * 40
        detail = {"number": 1, "url": "https://github.com/disposable/proof/pull/1", "state": "OPEN", "isDraft": False, "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN", "reviewDecision": "", "headRefOid": sha, "baseRefName": "main", "isCrossRepository": False, "commits": []}
        task["branch"] = "proof"
        h.pull_requests_of = lambda t: ("disposable/proof", [{"number": 1, "state": "OPEN", "headRefName": "proof", "isCrossRepository": False}])
        h.thread_repo = lambda t: "disposable/proof"
        h.own_branch = lambda t: "proof"
        h.gh_json = lambda args: dict(detail)
        h.checks_verdict = lambda repo, number: (True, None, {"count": 1, "state": "green"})
        h.merge_method = lambda repo: ("squash", {"source": "disposable proof"})
        result = self.rpc("emp_thread_merge", threadId=task["threadId"], dryRun=True)
        print("DRY RUN", json.dumps(result, sort_keys=True))
        self.assertTrue(result["dryRun"])
        gate = result["evidence"]["reviewGate"]
        self.assertEqual(gate["model"], fallback)
        self.assertEqual(gate["runId"], review["runs"][-1]["runId"])
        original = h.revision_inputs(result["evidence"])
        gate.update(model="other", runId="other")
        self.assertEqual(h.revision_inputs(result["evidence"]), original)
        self.assertNotIn("model", original)
        self.assertNotIn("runId", original)
        normal_review = self.launch(title="MO-147 normal review", taskType="review")
        normal_proc = self.wait_started(normal_review)
        h.handle_update(normal_review["sessionId"], {"sessionUpdate": "agent_message_chunk", "content": {"text": "Checked all changes and the builder proof.\nVERDICT: PASS"}})
        normal_proc.proc.terminate()
        self.until(lambda: not normal_review["activeRunId"])
        normal = self.rpc("emp_thread_merge", threadId=task["threadId"], dryRun=True)
        self.assertEqual(normal["evidence"]["reviewGate"]["model"], "subscriptions/claude-opus-5-5")
        print("NORMAL DRY RUN", json.dumps(normal, sort_keys=True))


def wall_clock_proof():
    proof = TurnBudgetProof()
    proof.setUp()
    try:
        first = proof.launch(turnSeconds=600)
        first_proc = proof.wait_started(first)
        second = proof.launch(title="wall-clock concurrent", turnSeconds=600)
        second_proc = proof.wait_started(second)
        h = proof.hub
        started = max(h.runtime_of(t["threadId"])["turnStartedAt"] for t in (first, second))
        print("WALL CLOCK: two concurrent real sleep processes; 601 actual seconds; no clock offset", flush=True)
        threading.Event().wait(max(0, started + 601 - time.time()))
        proof.assertEqual(proof.clock.offset, 0)
        for thread, proc in ((first, first_proc), (second, second_proc)):
            record = proof.expire(thread)
            proof.assertEqual((record["status"], record["error"]), ("failed", "turn budget exceeded: 10 min"))
            proof.assertEqual(proc.cancels, 1)
            proof.assertEqual(proof.releases.count(thread["threadId"]), 1)
            persisted = json.loads(Path(h.THREADS.path).read_text())[thread["threadId"]]
            proof.assertEqual(persisted["runs"][-1], record)
        print("WALL CLOCK PASS: both concurrent runs expired; one cancellation/engine release each; failed records persisted", flush=True)
    finally:
        proof.doCleanups()


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--wall-clock"]:
        wall_clock_proof()
    else:
        unittest.main(verbosity=2)
