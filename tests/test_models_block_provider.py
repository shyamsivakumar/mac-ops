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


def pick(name):
    return {"instanceId": name, "model": "m"}


class BlockProviderTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.file = self.dir / models.BLOCKED_FILE
        patcher = patch.dict(os.environ, {"COORDQ_DIR": tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def blocked(self):
        return json.loads(self.file.read_text())["blocked"]

    def test_expiry_on_read_and_manual_entries_kept(self):
        self.file.write_text(json.dumps({"blocked": {"manual:m": {"reason": "x"}, "bare:m": True}}))
        models.block_provider(pick("a"), 160, now=100)
        self.assertEqual(models.blocked_identities(now=159), {"a:m", "manual:m", "bare:m"})
        self.assertEqual(models.blocked_identities(now=160), {"manual:m", "bare:m"})

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
