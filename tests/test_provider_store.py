"""Replay tests for the store one provider block record lives in.

The store is one file beside the queue, replaced whole rather than edited
in place, and its read-modify-write is guarded by its own lock.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "coordinator" / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import provider_store


class ProviderStoreTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.previous = os.environ.get("COORDQ_DIR")
        os.environ["COORDQ_DIR"] = self.scratch.name
        self.addCleanup(self.restore)

    def restore(self):
        if self.previous is None:
            os.environ.pop("COORDQ_DIR", None)
        else:
            os.environ["COORDQ_DIR"] = self.previous

    def test_a_missing_store_holds_no_blocks(self):
        self.assertEqual(provider_store.read(), {})

    def test_the_store_is_one_file_beside_the_queue(self):
        self.assertEqual(provider_store.path(),
                         os.path.join(self.scratch.name, "providers-blocked.json"))

    def test_a_written_record_reads_back(self):
        record = {"reason": "no credits", "since": "2026-11-18T10:00:00+00:00",
                  "until": "2026-11-18T11:00:00+00:00", "by": "test"}
        provider_store.write({"glm:glm-5.3": record})
        self.assertEqual(provider_store.read(), {"glm:glm-5.3": record})
        with open(provider_store.path()) as f:
            self.assertEqual(json.load(f), {"blocked": {"glm:glm-5.3": record}})

    def test_a_store_that_is_not_the_store_raises(self):
        with open(provider_store.path(), "w") as f:
            f.write('{"blocked": []}')
        with self.assertRaises(ValueError):
            provider_store.read()

    def test_a_failure_time_keeps_its_whole_precision(self):
        """The failure time orders one refusal against another, so rounding
        it up would lose a refusal that came a fraction of a millisecond
        later."""
        self.assertEqual(provider_store.stamp(1794996000.0001),
                         "2026-11-18T10:00:00.000100+00:00")
        self.assertEqual(provider_store.stamp(1794996000), "2026-11-18T10:00:00+00:00")

    def test_an_expiry_is_written_in_whole_milliseconds_rounded_up(self):
        """The pi reader parses the expiry with Date.parse, which reads
        milliseconds only, so a sub-millisecond expiry is rounded up and the
        two readers read one instant."""
        self.assertEqual(provider_store.stamp_expiry(1794996000.0009),
                         "2026-11-18T10:00:00.001+00:00")
        self.assertEqual(provider_store.stamp_expiry(1794996000), "2026-11-18T10:00:00+00:00")

    def test_a_time_is_read_back_as_epoch_seconds(self):
        self.assertEqual(provider_store.parse_time("2026-11-18T10:00:00+00:00"), 1794996000.0)
        self.assertIsNone(provider_store.parse_time("not a time"))
        self.assertIsNone(provider_store.parse_time(None))

    def test_a_record_that_names_no_end_is_a_record_with_no_end(self):
        """A store written by hand, before this module existed, names no
        end: it is not a block that may be dropped."""
        self.assertIsNone(provider_store.until_of({"reason": "manual"}))
        self.assertEqual(provider_store.until_of({"until": "2026-11-18T11:00:00+00:00"}),
                         1794999600.0)

    def test_the_failure_time_of_a_record_is_read_back(self):
        self.assertEqual(
            provider_store.failure_time_of({"since": "2026-11-18T10:00:00+00:00"}),
            1794996000.0)
        self.assertIsNone(provider_store.failure_time_of({"reason": "manual"}))

    def test_the_lock_is_one_lock_for_the_store(self):
        with provider_store.locked():
            self.assertTrue(os.path.exists(provider_store.lock_path()))


if __name__ == "__main__":
    unittest.main()
