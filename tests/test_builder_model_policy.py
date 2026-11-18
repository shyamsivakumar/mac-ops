"""The builder-eligibility rules of MO-1063 (mac-ops #497).

Builds run only on the permitted builder selections — GLM 5.3, MiniMax,
DeepSeek or a task/* route on the router — so coordq refuses every other
explicit selection (any OpenAI model in any spelling, Opus, Sonnet,
cursor) for launches that do not declare taskType review, and ticket
refuses a builder:* label that is not on the config's permit list. Both
CLIs are scripts without a .py suffix, so they are loaded by path.
"""
import argparse
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "coordinator" / "bin"))
sys.path.insert(0, str(ROOT / "coordinator" / "overnight"))


def load(name, path):
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


coordq = load("coordq_policy_check", ROOT / "coordinator" / "bin" / "coordq")
ticket = load("ticket_policy_check", ROOT / "coordinator" / "bin" / "ticket")
lane = load("lane_policy_check", ROOT / "coordinator" / "overnight" / "lane_driver.py")
CONFIG = json.loads((ROOT / "coordinator" / "config" / "tickets.json").read_text())

# The pi task routes the ticket names (mac-ops #497, item 3). A router
# builder may name one of these five and nothing else.
NAMED_TASK_ROUTES = ("task/standard", "task/ui", "task/research", "task/rca", "task/chore")

# The gate chain carries no taskType exemption: only a declared review may
# name a gate model. The subscriptions/ spelling of a gate model (the form
# the cockpit reads back from executed runs) is a builder refusal too.
NON_BUILDERS = (
    {"instanceId": "openai-api", "model": "openai/gpt-6.2-astra"},
    {"instanceId": "codex", "model": "gpt-6.2-astra"},
    {"instanceId": "codex", "model": "subscriptions/gpt-6.2-astra"},
    {"instanceId": "codex", "model": "gpt-5.6-terra"},
    {"instanceId": "codex", "model": "gpt-6.1-sol"},
    {"instanceId": "codex", "model": "gpt-6-luna"},
    {"instanceId": "codex", "model": "o3"},
    {"instanceId": "pi", "model": "openai/gpt-6-astra"},
    {"instanceId": "claudeAgent", "model": "claude-sonnet-5-5"},
    {"instanceId": "claudeAgent", "model": "claude-opus-5-5"},
    {"instanceId": "cursor", "model": "default"},
    {"instanceId": "codex", "model": "zai-coding/glm-5.3"},
    {"instanceId": "pi", "model": "deepseek/deepseek-flash"},
    {"instanceId": "router", "model": "task/risky"},
)

# The five pi task routes the ticket names, and only those, are permitted
# router builders. task/risky and every other route are refused.
BUILDERS = (
    {"instanceId": "glm", "model": "zai/glm-5.3"},
    {"instanceId": "minimax", "model": "minimax/MiniMax-M3.1-Flash"},
    {"instanceId": "router", "model": "task/standard"},
    {"instanceId": "router", "model": "task/ui"},
    {"instanceId": "router", "model": "task/research"},
    {"instanceId": "router", "model": "task/rca"},
    {"instanceId": "router", "model": "task/chore"},
)


class CoordqBuilderPermit(unittest.TestCase):
    def test_every_non_builder_selection_is_refused(self):
        for task_type in ("standard", "risky", "design", "large", None):
            for selection in NON_BUILDERS:
                with self.subTest(task_type=task_type, selection=selection):
                    resolved, refusal = coordq.with_model(
                        {"taskType": task_type, "modelSelection": selection})
                    self.assertIsNone(resolved)
                    self.assertIn("builds run only on GLM 5.3, MiniMax or a task/* route", refusal)

    def test_the_gate_models_pass_only_as_declared_reviews(self):
        for selection in coordq.REVIEWER_CHAIN:
            with self.subTest(selection=selection):
                resolved, refusal = coordq.with_model(
                    {"taskType": "review", "modelSelection": dict(selection)})
                self.assertIsNone(refusal)
                self.assertEqual(resolved["modelSelection"], selection)
                self.assertNotIn("taskType", resolved)
                for task_type in ("risky", None):
                    resolved, refusal = coordq.with_model(
                        {"taskType": task_type, "modelSelection": dict(selection)})
                    self.assertIsNone(resolved)
                    self.assertIn("builds run only on GLM 5.3", refusal)

    def test_the_permitted_builders_pass(self):
        for selection in BUILDERS:
            with self.subTest(selection=selection):
                resolved, refusal = coordq.with_model(
                    {"taskType": "risky", "modelSelection": selection})
                self.assertIsNone(refusal)
                self.assertEqual(resolved["modelSelection"], selection)

    def test_a_router_task_route_is_the_only_router_builder(self):
        resolved, refusal = coordq.with_model(
            {"taskType": "standard",
             "modelSelection": {"instanceId": "router", "model": "subscriptions/gpt-6.2-astra"}})
        self.assertIsNone(resolved)
        self.assertIn("builds run only on GLM 5.3", refusal)

    def test_only_the_five_named_pi_routes_are_permitted(self):
        # The ticket names five pi routes (standard, ui, research, rca,
        # chore). task/risky is not one of them: an explicit risky build
        # must be refused rather than passed to an unconfigured route.
        for route in ("task/standard", "task/ui", "task/research",
                      "task/rca", "task/chore"):
            with self.subTest(route=route):
                resolved, refusal = coordq.with_model(
                    {"taskType": "standard",
                     "modelSelection": {"instanceId": "router", "model": route}})
                self.assertIsNone(refusal)
                self.assertEqual(resolved["modelSelection"]["model"], route)
        for route in ("task/risky", "task/design", "task/large", "task/worker"):
            with self.subTest(route=route):
                resolved, refusal = coordq.with_model(
                    {"taskType": "standard",
                     "modelSelection": {"instanceId": "router", "model": route}})
                self.assertIsNone(resolved)
                self.assertIn("builds run only on GLM 5.3, MiniMax or a task/* route", refusal)

    def test_a_direct_deepseek_start_is_refused(self):
        # DeepSeek is a fallback inside a task/* route, never a start.
        resolved, refusal = coordq.with_model(
            {"taskType": "risky",
             "modelSelection": {"instanceId": "pi", "model": "deepseek/deepseek-flash"}})
        self.assertIsNone(resolved)
        self.assertIn("builds run only on GLM 5.3", refusal)


class TaskRouteAgreement(unittest.TestCase):
    """coordq and the lane driver keep the same five routes.

    The lane driver is a separate program from coordq, so the route list
    is written twice; this test is the tie between them, and the tie to
    the ticket.
    """

    def test_both_copies_are_the_five_named_routes(self):
        self.assertEqual(tuple(coordq.TASK_ROUTES), NAMED_TASK_ROUTES)
        self.assertEqual(tuple(lane.TASK_ROUTES), NAMED_TASK_ROUTES)

    def test_a_route_outside_the_five_is_refused_everywhere(self):
        # Fresh launch (coordq), fix-round continuation (lane) and dead
        # run relaunch (lane) all refuse a route the ticket does not name.
        for route in ("task/risky", "task/design", "task/large"):
            with self.subTest(route=route):
                resolved, refusal = coordq.with_model(
                    {"taskType": "standard",
                     "modelSelection": {"instanceId": "router", "model": route}})
                self.assertIsNone(resolved)
                self.assertIn("builds run only on GLM 5.3", refusal)
                self.assertFalse(lane.allowed_builder(
                    {"providerInstanceId": "router", "model": route}))
                self.assertEqual(
                    lane.dead_run_model(
                        {"providerInstanceId": "router", "model": route}),
                    lane.GLM)

    def test_the_five_named_routes_are_permitted_everywhere(self):
        for route in NAMED_TASK_ROUTES:
            with self.subTest(route=route):
                resolved, refusal = coordq.with_model(
                    {"taskType": "standard",
                     "modelSelection": {"instanceId": "router", "model": route}})
                self.assertIsNone(refusal)
                self.assertTrue(lane.allowed_builder(
                    {"providerInstanceId": "router", "model": route}))
                self.assertEqual(
                    lane.dead_run_model(
                        {"providerInstanceId": "router", "model": route}),
                    {"instanceId": "router", "model": route})


class TicketBuilderPermit(unittest.TestCase):
    def cfg(self):
        return {"types": CONFIG["types"], "models": CONFIG["models"],
                "builderAliases": CONFIG["builderAliases"]}

    def test_a_builder_label_can_only_pick_a_permitted_builder(self):
        for alias in ("sonnet", "astra", "cursor"):
            with self.subTest(alias=alias):
                with self.assertRaises(ticket.Refuse) as caught:
                    ticket.resolve_models(self.cfg(), {"type": "risky",
                                                       "builder": alias,
                                                       "reviewer": None})
                self.assertIn(f"builder {alias}", str(caught.exception))

    def test_the_type_defaults_resolve_to_permitted_builders(self):
        cfg = self.cfg()
        for ticket_type in cfg["types"]:
            if ticket_type == "review":
                continue
            with self.subTest(ticket_type=ticket_type):
                builder, reviewer = ticket.resolve_models(
                    cfg, {"type": ticket_type, "builder": None, "reviewer": None})
                self.assertIn(builder, cfg["builderAliases"])
                self.assertNotEqual(cfg["models"][builder]["vendor"], "openai")


class DispatchRoundTrip(unittest.TestCase):
    """A queued review survives dispatch: the marker stays in the queue and
    is stripped only from the payload sent to T3 (mac-ops #497)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.q = load("coordq_dispatch_check", ROOT / "coordinator" / "bin" / "coordq")
        self.q.DIR = self.tmp.name
        self.q.cap = lambda: 6
        # The queue is full, so the started item stays queued and readable.
        self.q.live = lambda: 6
        self.q.save({"next": 1, "items": []})
        stub = Path(self.tmp.name) / "t3mcp-stub"
        stub.write_text("#!/usr/bin/env python3\n"
                        "import os, sys\n"
                        "with open(os.environ['STUB_LOG'], 'a') as f:\n"
                        "    f.write(sys.stdin.read() + '\\n')\n"
                        "print('{\"ok\": true}')\n")
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        self.q.T3MCP = str(stub)
        self.log = Path(self.tmp.name) / "calls.log"
        os.environ["STUB_LOG"] = str(self.log)

    def test_a_queued_review_dispatches_and_strips_the_marker(self):
        payload = json.dumps({"taskType": "review", "message": "review the diff",
                              "modelSelection": dict(coordq.REVIEWER_CHAIN[0]),
                              "runtimeMode": "full-access"})
        args = argparse.Namespace(args=payload, title=None, priority=400,
                                  tool="t3_thread_launch", action_key=None)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.q.cmd_start(args)
        self.assertEqual(out.getvalue().strip(), "queued #1", err.getvalue())
        queued = self.q.load()["items"][0]["args"]
        # The declaration survives in the queue: a review stays a review.
        self.assertEqual(queued["taskType"], "review")
        # Dispatch validates the queued item and strips the marker for T3.
        code, result = self.q.call("t3_thread_launch", queued)
        self.assertEqual(code, 0, result)
        sent = json.loads(self.log.read_text().strip().splitlines()[-1])
        self.assertNotIn("taskType", sent)
        self.assertEqual(sent["modelSelection"], coordq.REVIEWER_CHAIN[0])

    def test_the_same_payload_without_the_marker_is_refused_at_dispatch(self):
        stripped = {"message": "review the diff",
                    "modelSelection": dict(coordq.REVIEWER_CHAIN[0]),
                    "runtimeMode": "full-access"}
        code, result = self.q.call("t3_thread_launch", stripped)
        self.assertEqual(code, 1)
        self.assertIn("builds run only on GLM 5.3", result)


if __name__ == "__main__":
    unittest.main()
