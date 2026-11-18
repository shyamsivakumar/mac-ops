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
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from unittest.mock import patch

BIN = Path(__file__).resolve().parents[1] / "coordinator" / "bin"
ROOT = Path(__file__).resolve().parents[1]
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install_coordinator
import models
import provider_block
import provider_reset


def load_coordq():
    """The queue script, loaded the way the other tests load it."""
    path = Path(__file__).resolve().parents[1] / "coordinator" / "bin" / "coordq"
    loader = SourceFileLoader("coordq_provider_block", str(path))
    spec = spec_from_loader(loader.name, loader)
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


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

    def test_a_reset_at_the_moment_of_the_failure_is_not_pushed_to_the_next_day(self):
        """A failure at the very moment the provider says it resets is not a
        failure that holds the provider for another day."""
        failed = moment("2026-11-18T14:00:00")
        self.assertEqual(provider_block.reset_at("resets at 14:00 UTC", failed), failed)
        record = provider_block.record_block(SELECTION, "429; resets at 14:00 UTC", failed,
                                              now=failed)
        self.assertIsNone(record)
        self.assertEqual(provider_block.blocked_identities(), set())

    def test_an_offset_wins_over_a_bare_utc(self):
        """'UTC+08:00' is eight hours ahead of UTC, not UTC."""
        failed = moment("2026-11-18T02:00:00")
        record = provider_block.record_block(
            SELECTION, "will reset at 2026-11-18 11:58:52 (UTC+08:00)", failed, now=failed)
        self.assertEqual(record["until"], "2026-11-18T03:58:52+00:00")

    def test_a_newer_zero_reset_frees_a_provider_held_until_later(self):
        """A 10:00 refusal blocks until 14:00; at 11:00 the provider says
        `retry after 0s` and is free from then on."""
        older = moment("2026-11-18T10:00:00")
        provider_block.record_block(SELECTION, "429; resets at 14:00 UTC", older, now=older)
        self.assertTrue(provider_block.is_blocked(SELECTION, moment("2026-11-18T11:00:00")))
        newer = moment("2026-11-18T11:00:00")
        record = provider_block.record_block(SELECTION, "rate limited, retry after 0s",
                                             newer, now=newer)
        self.assertIsNone(record)
        self.assertFalse(provider_block.is_blocked(SELECTION, moment("2026-11-18T11:00:01")))
        self.assertFalse(provider_block.is_blocked(SELECTION, moment("2026-11-18T13:59:59")))

    def test_a_late_replay_of_an_older_refusal_does_not_restore_the_block(self):
        """The store keeps the newer refusal, so the old one cannot come
        back and hold the provider again."""
        older = moment("2026-11-18T10:00:00")
        provider_block.record_block(SELECTION, "429; resets at 14:00 UTC", older, now=older)
        newer = moment("2026-11-18T11:00:00")
        provider_block.record_block(SELECTION, "rate limited, retry after 0s", newer, now=newer)
        provider_block.record_block(SELECTION, "429; resets at 14:00 UTC", older,
                                    now=moment("2026-11-18T11:30:00"))
        self.assertFalse(provider_block.is_blocked(SELECTION, moment("2026-11-18T13:59:59")))

    def test_a_newer_refusal_with_no_record_yet_is_not_undone_by_an_older_one(self):
        """With an empty store, an 11:00 `retry after 0s` is written, so a
        delayed 10:00 refusal that names 14:00 cannot block the provider."""
        newer = moment("2026-11-18T11:00:00")
        provider_block.record_block(SELECTION, "rate limited, retry after 0s", newer, now=newer)
        older = moment("2026-11-18T10:00:00")
        provider_block.record_block(SELECTION, "429; resets at 14:00 UTC", older,
                                    now=moment("2026-11-18T11:30:00"))
        self.assertFalse(provider_block.is_blocked(SELECTION, moment("2026-11-18T11:30:01")))
        self.assertFalse(provider_block.is_blocked(SELECTION, moment("2026-11-18T13:59:59")))

    def test_an_offset_a_clock_cannot_hold_is_not_a_zone(self):
        """`UTC+24:00` is no offset; reading it raised in the failure handler."""
        failed = moment("2026-11-18T10:00:00")
        record = provider_block.record_block(SELECTION, "429; resets at 14:00 UTC+24:00",
                                             failed, now=failed)
        self.assertEqual(record["until"], "2026-11-18T14:00:00+00:00")

    def test_a_reset_past_the_end_of_the_calendar_falls_back_to_the_default_hour(self):
        failed = moment("2026-11-18T10:00:00")
        record = provider_block.record_block(SELECTION, "429 retry after 99999999999999999s",
                                             failed, now=failed)
        self.assertEqual(record["until"], "2026-11-18T11:00:00+00:00")

    def test_a_newer_refusal_read_after_its_reset_clears_the_older_block(self):
        """A newer refusal whose reset has passed still replaces the older
        block, so the provider is not held until the older reset."""
        older = moment("2026-11-18T10:00:00")
        provider_block.record_block(SELECTION, "429; resets at 14:00 UTC", older, now=older)
        newer = moment("2026-11-18T11:00:00")
        provider_block.record_block(SELECTION, "429; resets at 11:05 UTC", newer,
                                    now=moment("2026-11-18T12:00:00"))
        self.assertFalse(provider_block.is_blocked(SELECTION, moment("2026-11-18T12:00:01")))
        self.assertFalse(provider_block.is_blocked(SELECTION, moment("2026-11-18T13:59:59")))

    def test_a_next_day_reset_in_a_named_zone_keeps_the_local_day(self):
        """A failure at 23:00 on October 31 with 'resets at 14:00
        America/Los_Angeles' blocks until 14:00 PST on November 1. Adding a
        day of seconds would give 13:00 PST: the clock changed."""
        base = moment("2026-11-01T06:00:00")
        got = provider_reset.reset_at("429; resets at 14:00 America/Los_Angeles", base)
        self.assertEqual(got, moment("2026-11-01T22:00:00"))

    def test_a_newer_refusal_replaces_an_older_reset(self):
        """The provider's latest word on when it comes back is the one that
        holds: an 11:00 refusal that names noon replaces a 10:00 record
        that named 14:00."""
        older = moment("2026-11-18T10:00:00")
        provider_block.record_block(SELECTION, "429; resets at 14:00 UTC", older, now=older)
        newer = moment("2026-11-18T11:00:00")
        record = provider_block.record_block(SELECTION, "429; resets at 12:00 UTC", newer,
                                             now=newer)
        self.assertEqual(record["since"], "2026-11-18T11:00:00+00:00")
        self.assertEqual(record["until"], "2026-11-18T12:00:00+00:00")
        self.assertTrue(provider_block.is_blocked(SELECTION, moment("2026-11-18T11:59:59")))
        self.assertFalse(provider_block.is_blocked(SELECTION, moment("2026-11-18T12:00:01")))

    def test_an_iso_reset_keeps_its_fractional_second(self):
        """A reset at 14:00:00.500 is half a second past 14:00:00, and the
        whole timestamp is read."""
        failed = moment("2026-11-18T10:00:00")
        record = provider_block.record_block(
            SELECTION, "usage limit; resets at 2026-11-18T14:00:00.500Z", failed, now=failed)
        self.assertEqual(record["until"], "2026-11-18T14:00:00.500000+00:00")

    def test_an_iso_reset_with_a_fraction_and_an_offset(self):
        failed = moment("2026-11-18T10:00:00")
        record = provider_block.record_block(
            SELECTION, "usage limit; resets at 2026-11-18T14:00:00.500+02:00", failed, now=failed)
        self.assertEqual(record["until"], "2026-11-18T12:00:00.500000+00:00")

    def test_a_time_of_day_reset_keeps_its_fractional_second(self):
        failed = moment("2026-11-18T10:00:00")
        record = provider_block.record_block(
            SELECTION, "usage limit; resets at 14:00:00.500 UTC", failed, now=failed)
        self.assertEqual(record["until"], "2026-11-18T14:00:00.500000+00:00")

    def test_the_pi_reader_honours_the_end_of_a_block(self):
        """The generated route check reads the same store, so a block whose
        reset has passed may not skip a provider there and free it here."""
        generated = install_coordinator.SHARED_BLOCKS
        self.assertIn("until", generated)
        self.assertIn("Date.now()", generated)

    def test_the_failure_handler_records_the_block_of_a_failed_run(self):
        """A run that failed with a provider error is a block, and the block
        starts when the run failed."""
        value = {"thread": {"threadId": "t1", "status": "failed", "latestRunId": "r1",
                            "providerInstanceId": "glm", "model": "zai/glm-5.3",
                            "completedAt": "2026-11-18T10:35:00+00:00"},
                 "recentRuns": [{"runId": "r1", "status": "failed",
                                 "startedAt": "2026-11-18T10:00:00+00:00",
                                 "completedAt": "2026-11-18T10:35:00+00:00",
                                 "error": {"code": "429",
                                           "message": "429 rate limit; resets in 30 minutes"}}]}
        record = provider_block.block_run(SELECTION, value, now=moment("2026-11-18T10:35:00"))
        self.assertEqual(record["since"], "2026-11-18T10:35:00+00:00")
        self.assertEqual(record["until"], "2026-11-18T11:05:00+00:00")
        self.assertTrue(provider_block.is_blocked(SELECTION, moment("2026-11-18T10:40:00")))

    def test_a_failure_that_is_not_the_provider_writing_nothing(self):
        value = {"thread": {"status": "failed", "latestRunId": "r1"},
                 "recentRuns": [{"runId": "r1", "status": "failed",
                                 "completedAt": "2026-11-18T10:35:00+00:00",
                                 "error": {"message": "worker 14031 exited"}}]}
        self.assertIsNone(provider_block.block_run(SELECTION, value))

    def test_an_older_failure_does_not_shorten_a_newer_block(self):
        """A failure read late may not free a provider a newer failure
        blocked for longer."""
        newer = moment("2026-11-18T12:00:00")
        provider_block.record_block(SELECTION, "429; resets at 14:00 UTC", newer, now=newer)
        older = moment("2026-11-18T10:35:00")
        record = provider_block.record_block(SELECTION, "resets in 30 minutes", older,
                                             now=moment("2026-11-18T11:00:00"))
        self.assertEqual(record["until"], "2026-11-18T14:00:00+00:00")
        self.assertTrue(provider_block.is_blocked(SELECTION, moment("2026-11-18T13:59:59")))
        self.assertFalse(provider_block.is_blocked(SELECTION, moment("2026-11-18T14:00:01")))

    def test_a_reset_of_zero_frees_the_provider_at_once(self):
        """'retry after 0s' names a reset, and a reset of zero is now."""
        failed = moment("2026-11-18T10:35:00")
        self.assertEqual(provider_block.reset_at("rate limited, retry after 0s", failed), failed)
        record = provider_block.record_block(SELECTION, "rate limited, retry after 0s",
                                              failed, now=failed)
        self.assertIsNone(record)
        self.assertEqual(provider_block.blocked_identities(), set())

    def test_a_local_disk_error_blocks_nobody(self):
        """`disk quota exceeded` holds the words of a quota refusal and is
        a full disk, not the provider."""
        value = "disk quota exceeded"
        self.assertFalse(provider_block.provider_refusal("", value))
        self.assertIsNone(provider_block.block_run(SELECTION, value))
        self.assertEqual(provider_block.blocked_identities(), set())

    def test_a_leading_status_code_is_a_refusal(self):
        """A launch error arrives as plain text: '429; resets at 14:00 UTC'
        names the status it was refused with."""
        failed = moment("2026-11-18T10:00:00")
        record = provider_block.block_run(SELECTION, "429; resets at 14:00 UTC",
                                          now=failed)
        self.assertIsNotNone(record)
        self.assertEqual(record["until"], "2026-11-18T14:00:00+00:00")
        self.assertTrue(provider_block.is_blocked(SELECTION, moment("2026-11-18T13:59:59")))
        self.assertFalse(provider_block.is_blocked(SELECTION, moment("2026-11-18T14:00:01")))

    def test_a_number_inside_a_message_is_no_refusal(self):
        """`worker 14031 exited` holds the digits of 403 and is no refusal."""
        self.assertFalse(provider_block.provider_refusal("", "worker 14031 exited"))
        self.assertFalse(provider_block.provider_refusal("", "429 items queued"))

    def test_the_queue_writes_the_block_when_a_launch_fails(self):
        """The production path: a launch that fails with a provider error
        blocks that provider, so the next launch does not use it."""
        coordq = load_coordq()
        coordq.DIR = self.scratch.name
        coordq.live = lambda: 0
        coordq.cap = lambda: 6
        coordq.save({"next": 2, "items": [
            {"id": 1, "tool": "t3_thread_launch", "priority": 0, "title": "queued",
             "args": {"clientRequestId": "c1", "title": "queued", "projectId": "p",
                      "modelSelection": dict(SELECTION)}}]})
        with patch.object(coordq, "active_thread_ids", return_value=set()), \
                patch.object(coordq, "call",
                             return_value=(1, "429 rate limit; resets in 30 minutes")):
            coordq.drain()
        self.assertTrue(provider_block.is_blocked(SELECTION))
        record = provider_block.read()[IDENTITY]
        self.assertEqual(record["reason"], "429 rate limit; resets in 30 minutes")
        self.assertTrue(record["until"].endswith("+00:00"))

    def test_the_queue_blocks_on_the_ticket_literal_refusal(self):
        """The ticket's own message, arriving as plain text from a launch."""
        coordq = load_coordq()
        coordq.DIR = self.scratch.name
        coordq.live = lambda: 0
        coordq.cap = lambda: 6
        coordq.save({"next": 2, "items": [
            {"id": 1, "tool": "t3_thread_launch", "priority": 0, "title": "queued",
             "args": {"clientRequestId": "c1", "title": "queued", "projectId": "p",
                      "modelSelection": dict(SELECTION)}}]})
        with patch.object(coordq, "active_thread_ids", return_value=set()), \
                patch.object(coordq, "call",
                             return_value=(1, "429; resets at 14:00 UTC")):
            coordq.drain()
        record = provider_block.read().get(IDENTITY)
        self.assertIsNotNone(record)
        self.assertEqual(record["reason"], "429; resets at 14:00 UTC")
        self.assertTrue(provider_block.is_blocked(SELECTION))


if __name__ == "__main__":
    unittest.main()
