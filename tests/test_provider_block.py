"""Replay tests for the shared provider block record.

Every case here is a sequence a reviewer named: a run that failed at one
moment and says when it comes back, replayed through the store and read
back the way a caller reads it.
"""
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "coordinator" / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import models
import provider_block


def moment(text):
    """An ISO UTC moment as epoch seconds."""
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


SELECTION = {"instanceId": "glm", "model": "zai/glm-5.3"}
IDENTITY = "glm:glm-5.3"


class ProviderBlockTests(unittest.TestCase):
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

    def test_a_run_that_failed_at_1035_with_a_relative_reset_ends_at_1105(self):
        """The reviewer's case: a 10:00 run failing at 10:35 stays blocked
        until 11:05, and the 10:00 start says nothing about it."""
        run = {"startedAt": "2026-11-18T10:00:00+00:00",
               "completedAt": "2026-11-18T10:35:00+00:00",
               "error": {"code": "429", "message": "429 rate limit; resets in 30 minutes"}}
        failed = provider_block.failed_at(run)
        self.assertEqual(failed, moment("2026-11-18T10:35:00"))
        record = provider_block.record_block(
            SELECTION, run["error"]["message"], failed,
            now=moment("2026-11-18T10:35:00"))
        self.assertEqual(record["until"], "2026-11-18T11:05:00+00:00")
        self.assertTrue(provider_block.is_blocked(SELECTION, moment("2026-11-18T11:04:59")))
        self.assertFalse(provider_block.is_blocked(SELECTION, moment("2026-11-18T11:05:01")))

    def test_a_failure_read_late_keeps_the_window_it_named(self):
        """A block measured from the read would hold the provider past the
        reset the provider named."""
        failed = moment("2026-11-18T10:35:00")
        provider_block.record_block(SELECTION, "resets in 30 minutes", failed,
                                    now=moment("2026-11-18T11:00:00"))
        self.assertFalse(provider_block.is_blocked(SELECTION, moment("2026-11-18T11:05:01")))

    def test_an_absolute_reset_in_utc_blocks_until_that_hour(self):
        """The reviewer's case: '429; resets at 14:00 UTC' at 10:00 blocks
        until 14:00."""
        failed = moment("2026-11-18T10:00:00")
        record = provider_block.record_block(SELECTION, "429; resets at 14:00 UTC", failed,
                                              now=failed)
        self.assertEqual(record["until"], "2026-11-18T14:00:00+00:00")
        self.assertTrue(provider_block.is_blocked(SELECTION, moment("2026-11-18T13:59:59")))
        self.assertFalse(provider_block.is_blocked(SELECTION, moment("2026-11-18T14:00:01")))

    def test_a_relative_reset_in_seconds(self):
        failed = moment("2026-11-18T10:00:00")
        record = provider_block.record_block(SELECTION, "rate limited, retry after 3600s",
                                              failed, now=failed)
        self.assertEqual(record["until"], "2026-11-18T11:00:00+00:00")

    def test_an_iso_reset_is_taken_as_it_is_written(self):
        failed = moment("2026-11-18T10:00:00")
        record = provider_block.record_block(
            SELECTION, "usage limit; resets at 2026-11-18T11:58:52Z", failed, now=failed)
        self.assertEqual(record["until"], "2026-11-18T11:58:52+00:00")

    def test_the_glm_reset_is_read_in_the_zone_it_states(self):
        """GLM writes 'will reset at 2026-11-18 11:58:52' and names the
        zone it means."""
        failed = moment("2026-11-18T02:00:00")
        record = provider_block.record_block(
            SELECTION, "quota exhausted, will reset at 2026-11-18 11:58:52 (Asia/Shanghai)",
            failed, now=failed)
        self.assertEqual(record["until"], "2026-11-18T03:58:52+00:00")

    def test_a_reset_without_a_zone_is_read_as_utc(self):
        failed = moment("2026-11-18T02:00:00")
        record = provider_block.record_block(
            SELECTION, "will reset at 2026-11-18 11:58:52", failed, now=failed)
        self.assertEqual(record["until"], "2026-11-18T11:58:52+00:00")

    def test_a_failure_that_names_no_reset_is_blocked_for_an_hour(self):
        failed = moment("2026-11-18T10:00:00")
        record = provider_block.record_block(SELECTION, "no credits remaining",
                                              failed, now=failed)
        self.assertEqual(record["until"], "2026-11-18T11:00:00+00:00")
        self.assertTrue(provider_block.is_blocked(SELECTION, moment("2026-11-18T10:59:59")))
        self.assertFalse(provider_block.is_blocked(SELECTION, moment("2026-11-18T11:00:01")))

    def test_the_record_says_when_the_run_failed(self):
        failed = moment("2026-11-18T10:35:00")
        record = provider_block.record_block(SELECTION, "resets in 30 minutes", failed, now=failed)
        self.assertEqual(record["since"], "2026-11-18T10:35:00+00:00")
        self.assertEqual(record["reason"], "resets in 30 minutes")

    def test_a_start_time_is_never_the_failure_time(self):
        run = {"startedAt": "2026-11-18T10:00:00+00:00",
               "completedAt": "2026-11-18T10:35:00+00:00"}
        self.assertEqual(provider_block.failed_at(run), moment("2026-11-18T10:35:00"))
        run = {"startedAt": "2026-11-18T10:00:00+00:00"}
        self.assertIsNone(provider_block.failed_at(run))

    def test_a_window_that_has_already_closed_blocks_nobody(self):
        failed = moment("2026-11-18T10:00:00")
        record = provider_block.record_block(SELECTION, "resets in 30 minutes", failed,
                                              now=moment("2026-11-18T11:00:00"))
        self.assertIsNone(record)
        self.assertEqual(provider_block.blocked_identities(), set())

    def test_every_caller_reads_the_same_block(self):
        """The model list is what the queue, the lane driver and the ticket
        tool read, so a block one caller wrote is a block every caller sees."""
        failed = time.time() - 60
        provider_block.record_block(SELECTION, "no credits remaining", failed, now=failed)
        self.assertEqual(models.blocked_identities(), {IDENTITY})
        self.assertTrue(models.is_blocked(SELECTION))

    def test_a_block_whose_reset_has_passed_is_no_block(self):
        failed = moment("2026-11-18T10:00:00")
        provider_block.record_block(SELECTION, "resets in 30 minutes", failed, now=failed)
        self.assertEqual(provider_block.blocked_identities(moment("2026-11-18T10:29:59")),
                         {IDENTITY})
        self.assertEqual(provider_block.blocked_identities(moment("2026-11-18T10:30:01")), set())

    def test_a_record_without_an_end_is_blocked_until_it_is_taken_away(self):
        """A store written by hand, before this module existed, names no end."""
        provider_block.write({IDENTITY: {"reason": "manual", "since": "2026-11-18T10:00:00+00:00"}})
        self.assertEqual(provider_block.blocked_identities(), {IDENTITY})
        self.assertTrue(provider_block.is_blocked(SELECTION))


if __name__ == "__main__":
    unittest.main()
