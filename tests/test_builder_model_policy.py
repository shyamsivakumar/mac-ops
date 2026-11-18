"""The builder-eligibility rules of MO-1063 (mac-ops #497).

Builds run only on the permitted builder selections — GLM 5.3, MiniMax,
DeepSeek or a task/* route on the router — so coordq refuses every other
explicit selection (any OpenAI model in any spelling, Opus, Sonnet,
cursor) for launches that do not declare taskType review, and ticket
refuses a builder:* label that is not on the config's permit list. Both
CLIs are scripts without a .py suffix, so they are loaded by path.
"""
import importlib.util
import json
import sys
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "coordinator" / "bin"))


def load(name, path):
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


coordq = load("coordq_policy_check", ROOT / "coordinator" / "bin" / "coordq")
ticket = load("ticket_policy_check", ROOT / "coordinator" / "bin" / "ticket")
CONFIG = json.loads((ROOT / "coordinator" / "config" / "tickets.json").read_text())

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
)

BUILDERS = (
    {"instanceId": "glm", "model": "zai/glm-5.3"},
    {"instanceId": "minimax", "model": "minimax/MiniMax-M3.1-Flash"},
    {"instanceId": "router", "model": "task/standard"},
    {"instanceId": "router", "model": "task/risky"},
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

    def test_a_direct_deepseek_start_is_refused(self):
        # DeepSeek is a fallback inside a task/* route, never a start.
        resolved, refusal = coordq.with_model(
            {"taskType": "risky",
             "modelSelection": {"instanceId": "pi", "model": "deepseek/deepseek-flash"}})
        self.assertIsNone(resolved)
        self.assertIn("builds run only on GLM 5.3", refusal)


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


if __name__ == "__main__":
    unittest.main()
