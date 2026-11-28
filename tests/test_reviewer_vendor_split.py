import os
import tempfile
import unittest
from unittest.mock import patch
from tests.test_gatekeep_backstop_reviewer import load_coordq


def setUpModule():
    queue = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(queue.cleanup)
    environment = patch.dict(os.environ, {"COORDQ_DIR": queue.name})
    environment.start()
    unittest.addModuleCleanup(environment.stop)


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


class GateVerdictBuilderModelTest(unittest.TestCase):
    def _load_lane(self):
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        for p in (str(root / "coordinator" / "overnight"), str(root / "coordinator" / "bin")):
            if p not in sys.path:
                sys.path.insert(0, p)
        import lane_driver
        return lane_driver

    def test_coordq_receipt_and_journal_verdict_builder_model(self):
        import json
        from pathlib import Path

        q = load_coordq()
        lane = self._load_lane()
        receipts = {}
        q.record_gate_builder_models(receipts, "mcp:t-1", {"builderModels": ["  gpt-6.2-sol ", "", None, "gemini-4-neon"]})
        self.assertEqual(receipts["builder_model:mcp:t-1"], "gpt-6.2-sol")
        self.assertEqual(receipts["builder_models:mcp:t-1"], ["gpt-6.2-sol", "gemini-4-neon"])
        q.record_gate_builder_models(receipts, "mcp:t-empty", {"builderModels": ["", None]})
        self.assertNotIn("builder_model:mcp:t-empty", receipts)

        with tempfile.TemporaryDirectory() as tmp:
            rpath = Path(tmp) / "dispatch-receipts.json"
            rpath.write_text(json.dumps({**receipts, "builder_models:mcp:t-fallback": ["gemini-4-neon"]}))
            jdir = Path(tmp) / "journal"
            jdir.mkdir()
            ledger = {}
            with patch.dict(os.environ, {"COORD_JOURNAL_DIR": str(jdir)}),                  patch.object(lane, "RECEIPTS", str(rpath)),                  patch.object(lane, "DRY", False),                  patch.object(lane, "settle_read_gate"):
                lane.journal_verdict("o/r", 10, "a" * 40, "PASS", {"threadId": "mcp:t-1"}, ledger)
                lane.journal_verdict("o/r", 11, "b" * 40, "PASS", {"threadId": "mcp:t-fallback"}, ledger)
                lane.journal_verdict("o/r", 12, "c" * 40, "PASS", {"threadId": "mcp:t-missing"}, ledger)
                rpath.write_text("{bad json")
                lane.journal_verdict("o/r", 13, "d" * 40, "PASS", {"threadId": "mcp:t-corrupt"}, ledger)
                with patch.object(lane, "DRY", True):
                    lane.journal_verdict("o/r", 14, "e" * 40, "PASS", {"threadId": "mcp:t-dry"}, ledger)
            files = list(jdir.glob("events-*.jsonl"))
            self.assertEqual(len(files), 1)
            rows = [json.loads(line) for line in files[0].read_text().splitlines() if line.strip()]
            self.assertEqual(len(rows), 4)
            self.assertEqual(rows[0]["data"]["builder_model"], "gpt-6.2-sol")
            self.assertEqual(rows[0]["data"]["builder_models"], ["gpt-6.2-sol", "gemini-4-neon"])
            self.assertEqual(rows[1]["data"]["builder_model"], "gemini-4-neon")
            self.assertNotIn("builder_model", rows[2]["data"])
            self.assertNotIn("builder_model", rows[3]["data"])
