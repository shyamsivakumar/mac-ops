import os
import tempfile
import unittest
from unittest.mock import patch
from tests.test_gatekeep_backstop_reviewer import load_coordq

SAVED_COORDQ_DIR = None


def setUpModule():
    """Point coordq at a temporary queue for the length of this module.

    `coordq` reads `COORDQ_DIR` when it is loaded, and the live queue's
    blocked-provider list is this machine's state, not the repository's
    model list. A provider blocked here would otherwise be read as the
    repository's own answer and fail a test that is about the split.
    """
    global SAVED_COORDQ_DIR
    SAVED_COORDQ_DIR = os.environ.get("COORDQ_DIR")
    os.environ["COORDQ_DIR"] = tempfile.mkdtemp(prefix="coordq-vendor-split-")


def tearDownModule():
    if SAVED_COORDQ_DIR is None:
        os.environ.pop("COORDQ_DIR", None)
    else:
        os.environ["COORDQ_DIR"] = SAVED_COORDQ_DIR


def review_selection(q, entry_id):
    return next(e["selection"] for e in q.model_list.entries("review") if e["id"] == entry_id)


class ReviewerVendorSplitTest(unittest.TestCase):
    def test_vendor_split(self):
        q = load_coordq()
        astra = review_selection(q, "astra-api")
        opus = review_selection(q, "opus-api")
        for model, expected in [('claude-sonnet-5', astra),
                                ('gpt-6.1-sol', opus),
                                ('o4-mini', opus),
                                ('openai-codex/o3', opus),
                                ('gpt-6.1-terra', opus),
                                ('gpt-5.6-luna', opus),
                                ('minimax/MiniMax-M3', astra),
                                ('deepseek-v4', astra),
                                ('glm-5', astra),
                                ('cursor', astra),
                                ('unknown', astra)]:
            with self.subTest(model=model):
                self.assertEqual(q.reviewer_model([model]), expected)
                with patch.object(q, "builder_models", return_value=[model]):
                    self.assertEqual(q.backstop_model({}, []), astra)

    def test_unknown_routes(self):
        q = load_coordq()
        astra = review_selection(q, "astra-api")
        for route in (['claude-sonnet-5'],
                      ['claude-sonnet-5', 'gpt-6.1-terra'],
                      ['openai/gpt-6.1-sol'],
                      ['minimax/MiniMax-M3']):
            with self.subTest(route=route), patch.object(q, 'builder_models', return_value=[]), patch.object(q, 'router_chain', return_value=route):
                self.assertEqual(q.backstop_model({'providerInstanceId': 'router', 'model': 'task/test'}, []), astra)

    def test_unknown_builder_fallback(self):
        q = load_coordq()
        self.assertEqual(q.backstop_model({}, []), review_selection(q, "astra-api"))

    def test_head_refusal(self):
        q = load_coordq()
        self.assertFalse(q.check_names_head("Builder check: PASS old", "new", None, []))
        self.assertTrue(q.check_names_head("Builder check: PASS new", "new", None, []))
