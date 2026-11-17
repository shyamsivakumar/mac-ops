"""The builder-eligibility rules of MO-1063 (mac-ops #497).

No OpenAI model ever builds: coordq refuses an explicit OpenAI builder
selection for every taskType but review, and ticket refuses a builder:*
label that names an OpenAI vendor alias. Both CLIs are scripts without a
.py suffix, so they are loaded by path.
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


class CoordqBuilderGuard(unittest.TestCase):
    def test_a_risky_launch_cannot_select_sol(self):
        args = {"taskType": "risky",
                "modelSelection": {"instanceId": "codex", "model": "gpt-6.1-sol"}}
        resolved, refusal = coordq.with_model(args)
        self.assertIsNone(resolved)
        self.assertIn("builds run on GLM 5.3 or the MiniMax route", refusal)
        self.assertIn("gpt-6.1-sol", refusal)

    def test_every_openai_builder_selection_is_refused(self):
        # An omitted taskType is not evidence of a gate: the exact API Astra
        # selection is refused too unless the launch says taskType review.
        for task_type in ("standard", "risky", "design", "large", None):
            for selection in ({"instanceId": "openai-api", "model": "openai/gpt-6.2-astra"},
                              {"instanceId": "codex", "model": "gpt-6.2-astra"},
                              {"instanceId": "codex", "model": "gpt-6-luna"},
                              {"instanceId": "codex", "model": "gpt-6.1-terra"}):
                with self.subTest(task_type=task_type, selection=selection):
                    resolved, refusal = coordq.with_model(
                        {"taskType": task_type, "modelSelection": selection})
                    self.assertIsNone(resolved)
                    self.assertIn("never on an OpenAI model", refusal)

    def test_the_gate_models_pass_only_as_declared_reviews(self):
        for selection in coordq.REVIEWER_CHAIN:
            with self.subTest(selection=selection):
                resolved, refusal = coordq.with_model(
                    {"taskType": "review", "modelSelection": dict(selection)})
                self.assertIsNone(refusal)
                self.assertEqual(resolved["modelSelection"], selection)
                self.assertNotIn("taskType", resolved)
                resolved, refusal = coordq.with_model({"modelSelection": dict(selection)})
                self.assertIsNone(resolved)
                self.assertIn("never on an OpenAI model", refusal)

    def test_allowed_builders_pass(self):
        for selection in ({"instanceId": "glm", "model": "zai/glm-5.3"},
                          {"instanceId": "minimax", "model": "minimax/MiniMax-M3.1-Flash"},
                          {"instanceId": "router", "model": "task/standard"}):
            with self.subTest(selection=selection):
                resolved, refusal = coordq.with_model(
                    {"taskType": "risky", "modelSelection": selection})
                self.assertIsNone(refusal)
                self.assertEqual(resolved["modelSelection"], selection)


class TicketBuilderGuard(unittest.TestCase):
    def cfg(self):
        return {"types": CONFIG["types"], "models": CONFIG["models"]}

    def test_a_builder_label_cannot_pin_an_openai_model(self):
        with self.assertRaises(ticket.Refuse) as caught:
            ticket.resolve_models(self.cfg(), {"type": "chore",
                                               "builder": "astra",
                                               "reviewer": "sonnet"})
        self.assertIn("builder astra is an OpenAI model", str(caught.exception))

    def test_the_type_defaults_resolve_to_allowed_builders(self):
        cfg = self.cfg()
        for ticket_type, expected in (("risky", "glm-5.3"), ("design", "glm-5.3"),
                                      ("standard", "pi-standard"), ("chore", "pi-chore")):
            with self.subTest(ticket_type=ticket_type):
                builder, reviewer = ticket.resolve_models(
                    cfg, {"type": ticket_type, "builder": None, "reviewer": None})
                self.assertEqual(builder, expected)
                self.assertNotEqual(cfg["models"][builder]["vendor"], "openai")


if __name__ == "__main__":
    unittest.main()
