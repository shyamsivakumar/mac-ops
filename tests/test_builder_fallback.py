"""A builder that runs out moves the work to the next builder (MO-1082).

The replay of the two errors that killed the builds on 2026-11-17: GLM's
5-hour limit (429 code 1308) and MiniMax's Token Plan limit (429 code
2056). The blocked builder is held for every new build and send, the next
build starts on the next builder in the list, and one small probe an hour
frees the builder once it answers.
"""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "coordinator" / "bin"))

import builders
import provider_health

GLM = {"instanceId": "glm", "model": "zai/glm-5.3"}
MINIMAX = {"instanceId": "minimax", "model": "minimax/MiniMax-M3.1-Flash"}
DEEPSEEK = {"instanceId": "pi", "model": "deepseek/deepseek-flash"}


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        previous = os.environ.get("COORDQ_DIR")
        os.environ["COORDQ_DIR"] = self.scratch.name

        def restore():
            if previous is None:
                os.environ.pop("COORDQ_DIR", None)
            else:
                os.environ["COORDQ_DIR"] = previous
        self.addCleanup(restore)


class ErrorReplayTests(StoreCase):
    def test_glm_1308_is_a_blocking_reason(self):
        text = ('{"error": {"code": 1308, "message": "429 usage limit: '
                'the 5-hour limit is reached, resets in 2 hours"}}')
        self.assertEqual(provider_health.block_reason(text), "1308")
        self.assertIsNotNone(provider_health.reset_time(text))

    def test_minimax_2056_is_a_blocking_reason(self):
        text = ("429 code 2056: MiniMax Token Plan usage limit reached. "
                "Upgrade or wait for the plan reset.")
        self.assertEqual(provider_health.block_reason(text), "2056")

    def test_an_ordinary_failure_is_not(self):
        self.assertIsNone(provider_health.block_reason("VERDICT: FAIL\ncritical: the test was edited"))
        self.assertIsNone(provider_health.block_reason(""))


class FallbackTests(StoreCase):
    def test_next_build_goes_to_the_next_allowed_builder(self):
        line = builders.blocked_builder(GLM, "usage limit")
        self.assertIn("blocked provider glm:glm-5.3", line)
        self.assertEqual(builders.choose_builder(GLM), MINIMAX)

    def test_the_label_builder_comes_first_when_it_is_unblocked(self):
        self.assertEqual(builders.choose_builder(MINIMAX), MINIMAX)
        self.assertEqual(builders.choose_builder(None), GLM)

    def test_every_builder_blocked_returns_none(self):
        for member in builders.BUILDERS:
            builders.blocked_builder(member, "usage limit")
        self.assertIsNone(builders.choose_builder(GLM))

    def test_an_openai_or_sol_selection_is_not_a_builder(self):
        sol = {"instanceId": "codex", "model": "gpt-6.1-sol"}
        self.assertFalse(builders.is_builder(sol))
        self.assertEqual(builders.choose_builder(sol), GLM)

    def test_a_block_is_logged_once(self):
        first = builders.blocked_builder(GLM, "usage limit")
        second = builders.blocked_builder(GLM, "usage limit")
        self.assertTrue(first)
        self.assertIsNone(second)


class ProbeTests(StoreCase):
    def test_the_probe_waits_an_hour_after_a_block(self):
        now = 1000.0
        builders.blocked_builder(GLM, "usage limit", now=now)
        self.assertFalse(provider_health.probe_due(GLM, now=now + 60))
        self.assertTrue(provider_health.probe_due(GLM, now=now + provider_health.PROBE_INTERVAL))

    def test_the_reset_the_error_names_holds_the_probe_longer(self):
        now = 1000.0
        reset_at = now + 5 * provider_health.PROBE_INTERVAL
        builders.blocked_builder(GLM, "usage limit", now=now, reset_at=reset_at)
        self.assertFalse(provider_health.probe_due(GLM, now=now + provider_health.PROBE_INTERVAL))
        self.assertTrue(provider_health.probe_due(GLM, now=reset_at))

    def test_a_successful_probe_unblocks_the_builder(self):
        now = 1000.0
        builders.blocked_builder(GLM, "usage limit", now=now)
        providers = provider_health.note_probe(GLM, "builder-probe:glm:1", now=now)
        self.assertEqual(providers["probeRequestId"], "builder-probe:glm:1")
        self.assertTrue(provider_health.probe_due(GLM, now=now + 2 * provider_health.PROBE_INTERVAL))
        line = builders.recovered_builder(GLM, "builder-probe:glm:1")
        self.assertIn("unblocked provider glm:glm-5.3", line)
        self.assertEqual(builders.choose_builder(GLM), GLM)

    def test_an_older_probe_success_cannot_clear_a_newer_block(self):
        now = 1000.0
        builders.blocked_builder(GLM, "usage limit", now=now)
        provider_health.note_probe(GLM, "builder-probe:glm:1", now=now)
        self.assertIsNone(builders.recovered_builder(GLM, "builder-probe:glm:0"))
        self.assertTrue(provider_health.blocked(GLM))

    def test_a_failed_probe_waits_an_hour_from_the_failure(self):
        now = 1000.0
        builders.blocked_builder(GLM, "usage limit", now=now)
        provider_health.note_probe(GLM, "builder-probe:glm:1", now=now)
        provider_health.note_probe_failure(
            GLM, "429 usage limit, resets in 30 minutes", now=now + 10, request_id="builder-probe:glm:1")
        self.assertFalse(provider_health.probe_due(GLM, now=now + 15))
        self.assertTrue(provider_health.probe_due(GLM, now=now + 10 + provider_health.PROBE_INTERVAL))


class LaneDriverTests(StoreCase):
    """The lane driver never sends to a blocked builder's thread."""

    def load(self):
        from importlib.machinery import SourceFileLoader
        overnight = str(ROOT / "coordinator" / "overnight")
        if overnight not in sys.path:
            sys.path.insert(0, overnight)
        return SourceFileLoader("lane_driver_under_test",
                                str(ROOT / "coordinator" / "overnight" / "lane_driver.py")).load_module()

    def thread(self, model):
        return {"threadId": "t1", "status": "completed", "providerInstanceId": model["instanceId"],
                "model": model["model"], "worktreePath": "/tmp/wt", "pullRequests": []}

    def send_with(self, module, thread):
        from unittest.mock import patch
        calls = []

        def run(command, timeout=150):
            calls.append(command)
            return "#1 p0 started"

        with patch.object(module, "t3", lambda tool, args: {"thread": thread}), \
                patch.object(module, "run", run):
            out = module.send("t1", "Continue the work.", "MO#531 continue", {},
                              "check:shyamsivakumar/mac-ops#531:abc")
        return out, calls

    def module(self):
        module = self.load()
        module.DRY = False
        module.CFG = {"shyamsivakumar/mac-ops": {"projectId": "p", "key": "MO"}}
        return module

    def test_a_blocked_builders_thread_takes_no_send(self):
        module = self.module()
        builders.blocked_builder(GLM, "usage limit")
        # The thread's worktree is its own, so the work stays in it.
        with patch.object(module, "root_workspace", lambda thread: False):
            out, calls = self.send_with(module, self.thread(GLM))
        self.assertEqual(len(calls), 1)
        payload = __import__("json").loads(calls[0][2])
        self.assertEqual(payload["modelSelection"], MINIMAX)
        self.assertEqual(payload["workspaceStrategy"], {"type": "existing_worktree", "worktreePath": "/tmp/wt"})
        self.assertNotIn("threadId", payload)
        self.assertIn("fresh", out)

    def test_a_legacy_sol_thread_moves_the_build_to_a_builder(self):
        module = self.module()
        sol = {"instanceId": "codex", "model": "gpt-6.1-sol"}
        with patch.object(module, "root_workspace", lambda thread: False):
            out, calls = self.send_with(module, self.thread(sol))
        self.assertEqual(len(calls), 1)
        payload = json.loads(calls[0][2])
        self.assertEqual(payload["modelSelection"], GLM)
        self.assertEqual(payload["workspaceStrategy"], {"type": "existing_worktree", "worktreePath": "/tmp/wt"})
        self.assertNotIn("threadId", payload)
        self.assertIn("fresh", out)

    def test_a_legacy_sol_thread_in_a_shared_checkout_starts_no_build(self):
        module = self.module()
        sol = {"instanceId": "codex", "model": "gpt-6.1-sol"}
        with patch.object(module, "root_workspace", lambda thread: True):
            out, calls = self.send_with(module, self.thread(sol))
        self.assertEqual(calls, [])
        self.assertIn("no verified PR branch for relaunch", out)

    def test_an_unblocked_builders_thread_takes_the_send(self):
        module = self.module()
        out, calls = self.send_with(module, self.thread(GLM))
        self.assertEqual(calls[0][-1], "MO#531 continue")
        self.assertEqual(calls[0][4], "t3_thread_send")

    def test_every_builder_blocked_sends_nothing(self):
        module = self.module()
        for member in builders.BUILDERS:
            builders.blocked_builder(member, "usage limit")
        out, calls = self.send_with(module, self.thread(GLM))
        self.assertEqual(calls, [])
        self.assertIn("every builder is blocked", out)

    def probe_with(self, module, status, reply):
        from unittest.mock import patch
        calls = []

        def run(command, timeout=150):
            calls.append(command)
            return "#1 p950 started"

        def t3(tool, args):
            if args.get("view") == "messages":
                return {"items": [{"type": "assistant_message", "text": reply}] if reply else []}
            return {"thread": {"status": status}}

        with patch.object(module, "stall_receipts",
                          lambda: {"builder-probe:glm:1": "t-probe"}), \
                patch.object(module, "t3", t3), patch.object(module, "run", run):
            module.probe_blocked_builders({})
        return calls

    def blocked_glm_probe(self, now=None):
        now = time.time() if now is None else now
        builders.blocked_builder(GLM, "usage limit", now=now)
        provider_health.note_probe(GLM, "builder-probe:glm:1", now=now)
        return now

    def test_a_terminal_probe_without_an_answer_is_a_failed_probe(self):
        module = self.module()
        self.blocked_glm_probe()
        calls = self.probe_with(module, "completed", "")
        record = provider_health.record(GLM)
        self.assertNotIn("probeRequestId", record)
        self.assertIsNotNone(record.get("probeFailedAt"))
        self.assertTrue(provider_health.blocked(GLM))
        self.assertFalse(provider_health.probe_due(GLM))
        self.assertEqual(calls, [])

    def test_a_failed_probe_keeps_the_reset_its_error_names(self):
        module = self.module()
        self.blocked_glm_probe()
        self.probe_with(module, "failed",
                        "429 code 1308: the 5-hour limit is reached, resets in 2 hours")
        record = provider_health.record(GLM)
        self.assertNotIn("probeRequestId", record)
        self.assertAlmostEqual(record["resetAt"] - time.time(), 7200, delta=60)
        self.assertFalse(provider_health.probe_due(GLM))
        self.assertTrue(provider_health.probe_due(GLM, now=time.time() + 7200))

    def test_a_probe_that_never_reported_is_retried_at_its_deadline(self):
        module = self.module()
        self.blocked_glm_probe(now=time.time() - provider_health.PROBE_INTERVAL - 60)
        calls = self.probe_with(module, "running", "")
        self.assertEqual(len(calls), 1)
        self.assertIn('"clientRequestId": "builder-probe:', calls[0][2])
        self.assertNotEqual(provider_health.record(GLM).get("probeRequestId"), "builder-probe:glm:1")

    def dead_run_with(self, items):
        """Recover one dead thread whose messages are the ones given."""
        module = self.module()
        dead = {"threadId": "t-dead", "title": "ship #531", "settled": False}
        thread = {**dead, "providerInstanceId": DEEPSEEK["instanceId"], "model": DEEPSEEK["model"],
                  "worktreePath": "/tmp/fixture-worktree", "pullRequests": []}
        launched = []

        def t3(tool, args):
            if tool == "t3_thread_list":
                return {"threads": [dead]} if args.get("statuses") == ["failed", "interrupted"] else {"threads": []}
            if tool == "t3_thread_read" and args.get("view") == "messages":
                return {"items": items}
            if tool == "t3_thread_read":
                return {"thread": thread}
            if tool == "t3_thread_organize":
                return {}
            raise AssertionError(f"unexpected T3 call {tool}")

        def run(command, timeout=150):
            if command[0] == "git":
                return "worktree /tmp/fixture-worktree\n"
            launched.append(json.loads(command[2]))
            return "fixture-relaunch"

        with patch.object(module, "LANE_REPOS", ["shyamsivakumar/mac-ops"]), \
                patch.object(module, "CFG", {"shyamsivakumar/mac-ops": {"projectId": "p"}}), \
                patch.object(module, "DRY", False), patch.object(module, "t3", t3), \
                patch.object(module, "run", run), \
                patch.object(module, "stall_receipts",
                             return_value={"ticket:shyamsivakumar/mac-ops#531:a1": "t-dead"}), \
                patch.object(module, "read_json", return_value={"state": "OPEN"}):
            module.recover_dead_runs({})
        return launched

    def test_a_previous_runs_limit_does_not_block_the_builder(self):
        # The gate finding of round 5: recovery read the newest diagnostic in
        # the thread, so a run that stopped without one reused the 429 of the
        # run before it and blocked a healthy builder for every new build.
        launched = self.dead_run_with([
            {"runId": "run-a", "type": "error", "text": "429 code 1308 usage limit, resets in 2 hours"},
            {"runId": "run-b", "type": "user_message", "text": "Continue MO#531"},
            {"runId": "run-b", "type": "assistant_message", "text": "Reading the ticket"}])
        self.assertEqual(provider_health.load(), {})
        self.assertEqual(len(launched), 1)
        self.assertEqual(launched[0]["modelSelection"], DEEPSEEK)

    def test_a_block_reason_and_its_reset_come_from_the_failed_run(self):
        launched = self.dead_run_with([
            {"runId": "run-a", "type": "error", "text": "429 code 1308 usage limit, resets in 5 hours"},
            {"runId": "run-b", "type": "error",
             "text": "429 code 2056 MiniMax Token Plan usage limit, resets in 1 hours"},
            {"runId": "run-b", "type": "assistant_message", "text": "The plan resets in 5 hours"}])
        record = provider_health.record(DEEPSEEK)
        self.assertEqual(record.get("reason"), "2056")
        self.assertAlmostEqual(record["resetAt"] - time.time(), 3600, delta=120)
        self.assertEqual(len(launched), 1)
        self.assertEqual(launched[0]["modelSelection"], GLM)

    def test_a_thread_that_names_no_run_supplies_no_diagnostic(self):
        # Messages without a run id cannot be scoped, so they name no reason:
        # blocking a builder on one of them is the stale reading again.
        module = self.module()
        items = [{"type": "error", "text": "429 code 1308 usage limit"}]
        with patch.object(module, "t3", lambda tool, args: {"items": items}):
            self.assertEqual(module.last_reply("t1", diagnostics_only=True), "")

    def test_an_interrupted_reply_naming_authentication_blocks_nothing(self):
        # The gate finding of round 6: the builder's own last reply was read as
        # a diagnostic, so "I'm updating authentication tests" matched the
        # authentication marker and blocked the builder for every new build.
        # A progress reply is not a provider failure and names no block.
        launched = self.dead_run_with([
            {"runId": "run-a", "type": "user_message", "text": "Continue MO#531"},
            {"runId": "run-a", "type": "assistant_message", "text": "I'm updating authentication tests"}])
        self.assertEqual(provider_health.load(), {})
        self.assertEqual(len(launched), 1)
        self.assertEqual(launched[0]["modelSelection"], DEEPSEEK)

    def test_only_a_provider_failure_message_supplies_the_diagnostic(self):
        module = self.module()
        # The assistant reply sits last, so a reader that took the newest text
        # would return "I'm updating authentication tests" and let the
        # authentication marker block the builder again.
        items = [
            {"runId": "run-a", "type": "provider_error", "text": "401 invalid api key"},
            {"runId": "run-a", "type": "assistant_message", "text": "I'm updating authentication tests"}]
        with patch.object(module, "t3", lambda tool, args: {"items": items}):
            # The unfiltered reader is the path block_reason took before the fix:
            # it hands over the authentication reply.
            self.assertEqual(module.last_reply("t1"), "I'm updating authentication tests")
            self.assertEqual(module.last_reply("t1", diagnostics_only=True), "401 invalid api key")


class CallerTests(StoreCase):
    """Every caller falls back: the queue's dispatch and the ticket start."""

    def coordq(self):
        from importlib.machinery import SourceFileLoader
        return SourceFileLoader("coordq_under_test", str(ROOT / "coordinator/bin/coordq")).load_module()

    def queued(self, module, items):
        """A queue of items to dispatch in this case's scratch directory."""
        module.DIR = self.scratch.name
        module.live = lambda: 0
        module.cap = lambda: 6
        module.save({"next": 10, "items": items})

    def test_a_failed_probe_dispatch_never_moves_to_another_builder(self):
        # The replay of the gate finding: a probe dispatch that fails must
        # keep probing the provider it names. Moving it would spend another
        # builder on the probe and leave the blocked one unmeasured.
        # It is dispatched once and then retires: the health store's
        # deadline, not a retry storm, decides the next probe (MO-1082:
        # one small probe at most hourly).
        module = self.coordq()
        self.queued(module, [{"id": 1, "tool": "t3_thread_launch", "priority": 0,
                              "title": "Builder probe glm-5.3",
                              "args": {"projectId": "p", "title": "Builder probe",
                                       "modelSelection": dict(GLM),
                                       "clientRequestId": "builder-probe:glm:1"}}])
        calls = []

        def failing(tool, args, rules=None):
            calls.append((tool, dict(args)))
            return 1, "429 code 1308 usage limit: the 5-hour limit is reached, resets in 2 hours"

        with patch.object(module, "active_thread_ids", lambda: set()), \
                patch.object(module, "call", failing):
            module.drain()
        self.assertEqual(len(calls), 1)
        for tool, args in calls:
            self.assertEqual(tool, "t3_thread_launch")
            self.assertEqual(args["modelSelection"], GLM)
            self.assertEqual(args["clientRequestId"], "builder-probe:glm:1")
        self.assertEqual([item["id"] for item in module.load()["failed"]], [1])
        self.assertEqual(module.load()["items"], [])
        self.assertEqual(provider_health.load(), {})

    def test_a_failed_build_dispatch_moves_to_the_next_builder(self):
        # The same failure on a build is still a reroute: the guard covers
        # probes only.
        module = self.coordq()
        self.queued(module, [{"id": 2, "tool": "t3_thread_launch", "priority": 0,
                              "title": "ticket",
                              "args": {"projectId": "p", "title": "ticket",
                                       "modelSelection": dict(GLM), "clientRequestId": "build:2"}}])
        launches = []

        def dispatch(tool, args, rules=None):
            if tool != "t3_thread_launch":
                return 0, json.dumps({"thread": {"status": "completed"}})
            launches.append(dict(args))
            if len(launches) == 1:
                return 1, "429 code 1308 usage limit"
            return 0, json.dumps({"thread": {"threadId": "t-retry"}})

        with patch.object(module, "active_thread_ids", lambda: set()), \
                patch.object(module, "call", dispatch):
            module.drain()
        self.assertEqual(launches[0]["modelSelection"], GLM)
        self.assertEqual(launches[1]["modelSelection"], MINIMAX)
        self.assertTrue(provider_health.blocked(GLM))

    def test_a_failed_build_keeps_the_request_id_it_was_asked_with(self):
        # The fallback renames the retry, so the receipt keeps the request the
        # caller asked with as an alias: a lookup by that ID still finds the
        # thread that is running the build.
        module = self.coordq()
        self.queued(module, [{"id": 2, "tool": "t3_thread_launch", "priority": 0,
                              "title": "ticket",
                              "args": {"projectId": "p", "title": "ticket",
                                       "modelSelection": dict(GLM), "clientRequestId": "build:2"}}])
        launches = []

        def dispatch(tool, args, rules=None):
            if tool != "t3_thread_launch":
                return 0, json.dumps({"thread": {"status": "completed"}})
            launches.append(dict(args))
            if len(launches) == 1:
                return 1, "429 code 1308 usage limit"
            return 0, json.dumps({"thread": {"threadId": "t-retry"}})

        with patch.object(module, "active_thread_ids", lambda: set()), \
                patch.object(module, "call", dispatch):
            module.drain()
        with open(os.path.join(self.scratch.name, "dispatch-receipts.json")) as f:
            receipts = json.load(f)
        self.assertEqual(launches[1]["clientRequestId"], "build:2:" + MINIMAX["model"] + ":retry")
        self.assertEqual(receipts[launches[1]["clientRequestId"]], "t-retry")
        self.assertEqual(receipts["build:2"], "t-retry")

    def ticket(self):
        from importlib.machinery import SourceFileLoader
        return SourceFileLoader("ticket_under_test", str(ROOT / "coordinator/bin/ticket")).load_module()

    def test_a_failed_dispatch_blocks_its_builder_and_moves_the_build(self):
        module = self.coordq()
        self.assertIsNone(module.failed_builder(GLM, "VERDICT: FAIL"))
        self.assertEqual(module.failed_builder(GLM, "429 code 1308 usage limit"), MINIMAX)
        self.assertTrue(provider_health.blocked(GLM))

    def test_a_start_moves_to_the_next_builder(self):
        ticket = self.ticket()
        self.assertEqual(ticket.builder_model(GLM), GLM)
        builders.blocked_builder(GLM, "usage limit")
        self.assertEqual(ticket.builder_model(GLM), MINIMAX)

    def test_a_start_waits_when_every_builder_is_blocked(self):
        ticket = self.ticket()
        for member in builders.BUILDERS:
            builders.blocked_builder(member, "usage limit")
        with self.assertRaises(ticket.Refuse):
            ticket.builder_model(GLM)

    def test_a_start_moves_a_selection_outside_the_list_to_a_builder(self):
        # A label that names a Sol or OpenAI model must not start a build on
        # it, so the start runs on the first unblocked builder instead.
        ticket = self.ticket()
        sol = {"instanceId": "codex", "model": "gpt-6.1-sol"}
        self.assertEqual(ticket.builder_model(sol), GLM)

if __name__ == "__main__":
    unittest.main()
