import unittest
from unittest.mock import patch
from tests.test_gatekeep_backstop_reviewer import load_coordq


class ReviewerVendorSplitTest(unittest.TestCase):
    def test_vendor_split(self):
        q = load_coordq()
        for model, expected in [('claude-sonnet-5', q.ASTRA_MODEL),
                                ('gpt-6.1-sol', q.ASTRA_MODEL),
                                ('o4-mini', q.ASTRA_MODEL),
                                ('openai-codex/o3', q.ASTRA_MODEL),
                                ('gpt-6.1-terra', q.ASTRA_MODEL),
                                ('gpt-5.6-luna', q.ASTRA_MODEL),
                                ('minimax/MiniMax-M3', q.ASTRA_MODEL),
                                ('deepseek-v4', q.ASTRA_MODEL),
                                ('glm-5', q.ASTRA_MODEL),
                                ('cursor', q.ASTRA_MODEL),
                                ('unknown', q.ASTRA_MODEL)]:
            with self.subTest(model=model):
                self.assertEqual(q.reviewer_model([model]), expected)
                with patch.object(q, "builder_models", return_value=[model]):
                    self.assertEqual(q.backstop_model({}, []), expected)

    def test_unknown_routes(self):
        q = load_coordq()
        for route, expected in [(['claude-sonnet-5'], q.ASTRA_MODEL),
                                (['claude-sonnet-5', 'gpt-6.1-terra'], q.ASTRA_MODEL),
                                (['openai/gpt-6.1-sol'], q.ASTRA_MODEL),
                                (['minimax/MiniMax-M3'], q.ASTRA_MODEL)]:
            with self.subTest(route=route), patch.object(q, 'builder_models', return_value=[]), patch.object(q, 'router_chain', return_value=route):
                self.assertEqual(q.backstop_model({'providerInstanceId': 'router', 'model': 'task/test'}, []), expected)

    def test_unknown_builder_fallback(self):
        q = load_coordq()
        self.assertEqual(q.backstop_model({}, []), q.ASTRA_MODEL)

    def test_head_refusal(self):
        q = load_coordq()
        self.assertFalse(q.check_names_head("Builder check: PASS old", "new", None, []))
        self.assertTrue(q.check_names_head("Builder check: PASS new", "new", None, []))
