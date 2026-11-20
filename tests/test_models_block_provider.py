import datetime
import json
import os
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "coordinator" / "bin"))
import models  # noqa: E402

SEED = Path(__file__).resolve().parent.parent / "coordinator" / "models.json"


def pick(name, model="m"):
    return {"instanceId": name, "model": model}


def stamp(seconds):
    return datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc).isoformat()


class BlockProviderTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.file = self.dir / models.BLOCKED_FILE
        patcher = patch.dict(os.environ, {"COORDQ_DIR": tmp.name, "COORDINATOR_MODELS": str(SEED)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def blocked(self):
        return json.loads(self.file.read_text())["blocked"]

    def test_expiry_on_read_and_manual_entries_kept(self):
        self.file.write_text(json.dumps({"blocked": {"cursor:default": {"reason": "x"}, "codex:gpt-6.2-sol": True}}))
        models.block_provider(pick("codex", "gpt-6.1-terra"), 160, now=100)
        self.assertEqual(models.blocked_identities(now=159),
                         {"codex:gpt-6.1-terra", "cursor:default", "codex:gpt-6.2-sol"})
        self.assertEqual(models.blocked_identities(now=160), {"cursor:default", "codex:gpt-6.2-sol"})

    def test_until_only_entry_ends_at_its_until(self):
        self.file.write_text(json.dumps({"blocked": {
            "openai-api:gpt-6.2-astra": {"by": "provider_block", "until": stamp(160)},
        }}))
        self.assertEqual(models.blocked_identities(now=159), {"openai-api:gpt-6.2-astra"})
        self.assertEqual(models.blocked_identities(now=160), set())

    def test_until_is_read_only_when_expires_at_is_absent(self):
        self.file.write_text(json.dumps({"blocked": {
            "openai-api:gpt-6.2-astra": {"expires_at": 160, "until": stamp(900)},
        }}))
        self.assertEqual(models.blocked_identities(now=200), set())

    def test_until_accepts_a_z_suffix_and_a_bad_value_is_manual(self):
        self.file.write_text(json.dumps({"blocked": {
            "openai-api:gpt-6.2-astra": {"until": "1970-01-01T00:02:40Z"},
            "codex:gpt-6.2-sol": {"until": "not a time"},
        }}))
        self.assertEqual(models.blocked_identities(now=159),
                         {"openai-api:gpt-6.2-astra", "codex:gpt-6.2-sol"})
        self.assertEqual(models.blocked_identities(now=160), {"codex:gpt-6.2-sol"})

    def test_until_accepts_a_one_digit_and_a_nine_digit_fraction(self):
        self.file.write_text(json.dumps({"blocked": {
            "openai-api:gpt-6.2-astra": {"until": "1970-01-01T00:02:40.5+00:00"},
            "codex:gpt-6.2-sol": {"until": "1970-01-01T00:02:40.500000000+00:00"},
        }}))
        self.assertEqual(models.blocked_identities(now=160),
                         {"openai-api:gpt-6.2-astra", "codex:gpt-6.2-sol"})
        self.assertEqual(models.blocked_identities(now=161), set())

    def test_a_router_route_block_is_known_and_blocks_the_router_entry(self):
        self.file.write_text(json.dumps({"blocked": {"router:standard": {"expires_at": 900}}}))
        self.assertEqual(models.blocked_identities(now=100), {"router:standard"})
        self.assertTrue(models.entry_blocked(models.router_entry("build"), {"router:standard"}))
        self.assertEqual(models.first_available("build", None, {"router:standard"}, "standard")["id"], "cursor")

    def test_a_block_on_another_instance_is_pruned(self):
        self.file.write_text(json.dumps({"blocked": {"other:gpt-6.2-sol": {"expires_at": 900}}}))
        self.assertEqual(models.blocked_identities(now=100), set())

    def test_unknown_model_entry_is_pruned_and_a_manual_block_is_kept(self):
        self.file.write_text(json.dumps({"blocked": {
            "glm:glm-5.3": {"reason": "weekly limit"},
            "minimax:MiniMax-M3.1-Flash": {"reason": "usage limit"},
            "anthropic-api:claude-opus-5-5": {"reason": "credit balance too low"},
        }}))
        self.assertEqual(models.blocked_identities(now=100), {"anthropic-api:claude-opus-5-5"})

    def test_written_entry_carries_a_numeric_expires_at(self):
        self.file.write_text(json.dumps({"blocked": {
            "openai-api:gpt-6.2-astra": {"by": "provider_block", "until": stamp(160)},
        }}))
        models.block_provider(pick("openai-api", "openai/gpt-6.2-astra"), 900, now=100)
        entry = self.blocked()["openai-api:gpt-6.2-astra"]
        self.assertEqual(entry["expires_at"], 900)
        self.assertIsInstance(entry["expires_at"], (int, float))

    def test_a_longer_until_only_block_is_not_shortened_by_a_write(self):
        self.file.write_text(json.dumps({"blocked": {
            "openai-api:gpt-6.2-astra": {"until": stamp(900)},
        }}))
        models.block_provider(pick("openai-api", "openai/gpt-6.2-astra"), 160, now=100)
        self.assertEqual(self.blocked()["openai-api:gpt-6.2-astra"], {"until": stamp(900)})

    def test_an_expired_until_only_entry_is_dropped_on_write(self):
        self.file.write_text(json.dumps({"blocked": {
            "openai-api:gpt-6.2-astra": {"until": stamp(50)},
        }}))
        models.block_provider(pick("codex", "gpt-6.2-sol"), 160, now=100)
        self.assertEqual(set(self.blocked()), {"codex:gpt-6.2-sol"})

    def test_shorter_or_manual_block_never_replaces_a_longer_one(self):
        self.file.write_text(json.dumps({"blocked": {"manual:m": {"reason": "x"}, "a:m": {"expires_at": 700, "reason": "quota"}}}))
        models.block_provider(pick("manual"), 160, now=100)
        models.block_provider(pick("a"), 160, now=100)
        self.assertEqual(self.blocked(), {"manual:m": {"reason": "x"}, "a:m": {"expires_at": 700, "reason": "quota"}})
        models.block_provider(pick("a"), 900, now=100)
        self.assertEqual(self.blocked()["a:m"], {"expires_at": 900, "reason": "quota"})
        models.block_provider(pick("b"), 50, now=100)
        self.assertNotIn("b:m", self.blocked())

    def test_two_writers_keep_both_entries(self):
        def write(prefix):
            for i in range(25):
                models.block_provider(pick(f"{prefix}{i}"), 160, now=100)

        threads = [threading.Thread(target=write, args=(p,)) for p in "ab"]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(len(self.blocked()), 50)
        self.assertEqual([p.name for p in self.dir.glob(".*")], [])

    def test_corrupt_file_is_refused_and_left_alone(self):
        for raw in ("{not json", '{"blocked": []}', '{"blocked": {"old:m": {"expires_at": 5, "reason": NaN}}}'):
            self.file.write_text(raw)
            log = StringIO()
            with redirect_stderr(log), self.assertRaises(models.ModelsError):
                models.block_provider(pick("a"), 160, now=100)
            self.assertEqual((self.file.read_text(), len(log.getvalue().splitlines())), (raw, 1))

    def test_value_json_cannot_store_is_refused_before_replacing(self):
        raw = '{"blocked": {"manual:m": {"reason": 1e400}}}'
        self.file.write_text(raw)
        log = StringIO()
        with redirect_stderr(log), self.assertRaises(models.ModelsError):
            models.block_provider(pick("a"), 160, now=100)
        self.assertEqual((self.file.read_text(), len(log.getvalue().splitlines())), (raw, 1))
        self.assertEqual([p.name for p in self.dir.glob(".*")], [])
