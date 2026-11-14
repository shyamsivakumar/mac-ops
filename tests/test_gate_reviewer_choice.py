"""Tests for the reviewer of a gate.

Astra reviews every gate, whatever built the pull request. Opus is the one
failover, and only after an Astra gate died on a quota or a rate limit, so
the list is [Astra, Opus] and nothing else reviews.
"""
import unittest

from tests.test_gatekeep_backstop_reviewer import load_coordq

ASTRA = {"instanceId": "codex", "model": "gpt-6-astra"}
OPUS = {"instanceId": "claudeAgent", "model": "claude-opus-5-5"}
# Every other model the board runs, none of which may review a gate.
NOT_REVIEWERS = [
    {"instanceId": "pi", "model": "deepseek/deepseek-flash"},
    {"instanceId": "codex", "model": "gpt-6.1-sol"},
    {"instanceId": "minimax", "model": "minimax/MiniMax-M3.1-Flash"},
    {"instanceId": "codex", "model": "gpt-6.1-terra"},
    {"instanceId": "codex", "model": "gpt-5.6-luna"},
]


class GateReviewerTest(unittest.TestCase):
    def setUp(self):
        self.q = load_coordq()

    def test_the_reviewer_list_is_astra_then_opus(self):
        self.assertEqual(self.q.GATE_REVIEWERS, [ASTRA, OPUS])

    def test_no_other_model_is_a_reviewer(self):
        reviewers = [(model["instanceId"], model["model"]) for model in self.q.GATE_REVIEWERS]
        for model in NOT_REVIEWERS:
            with self.subTest(model=model["model"]):
                self.assertNotIn((model["instanceId"], model["model"]), reviewers)

    def test_the_review_task_type_runs_on_astra(self):
        self.assertEqual(self.q.TASK_MODELS["review"], ASTRA)

    def test_both_reviewers_are_gate_models(self):
        for model in (ASTRA, OPUS):
            with self.subTest(model=model["model"]):
                self.assertTrue(self.q.is_gate_model(model))

    def test_a_builder_model_is_not_a_gate_model(self):
        for model in NOT_REVIEWERS:
            with self.subTest(model=model["model"]):
                self.assertFalse(self.q.is_gate_model(model))
        self.assertFalse(self.q.is_gate_model(None))


if __name__ == "__main__":
    unittest.main()
