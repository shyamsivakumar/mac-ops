"""Replay tests for the reset a provider error names.

Every case is a sentence a provider wrote, and the moment that sentence
names, read the way a caller reads it.
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "coordinator" / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import provider_reset


def moment(text):
    """An ISO UTC moment as epoch seconds."""
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


class ProviderResetTests(unittest.TestCase):
    def test_a_relative_reset_is_measured_from_the_failure(self):
        """A run that failed at 10:35 and says 'resets in 30 minutes' comes
        back at 11:05, not at 11:05 plus however long the failure took to
        read."""
        base = moment("2026-11-18T10:35:00")
        self.assertEqual(provider_reset.reset_at("resets in 30 minutes", base),
                         moment("2026-11-18T11:05:00"))

    def test_a_relative_reset_in_seconds(self):
        base = moment("2026-11-18T10:00:00")
        self.assertEqual(provider_reset.reset_at("rate limited, retry after 3600s", base),
                         moment("2026-11-18T11:00:00"))

    def test_a_compound_relative_reset_is_read_whole(self):
        base = moment("2026-11-18T10:00:00")
        for message in ("429; resets in 1 hour 30 minutes", "429; retry after 1h 30m",
                        "429; resets in 1 hour and 30 minutes", "429; retry after 5400s"):
            self.assertEqual(provider_reset.reset_at(message, base),
                             moment("2026-11-18T11:30:00"), message)

    def test_a_relative_reset_in_days(self):
        base = moment("2026-11-18T10:00:00")
        self.assertEqual(provider_reset.reset_at("429; retry after 2 days", base),
                         moment("2026-11-20T10:00:00"))

    def test_a_reset_of_zero_is_a_reset(self):
        base = moment("2026-11-18T10:00:00")
        self.assertEqual(provider_reset.reset_at("rate limited, retry after 0s", base), base)

    def test_an_absolute_reset_in_utc(self):
        base = moment("2026-11-18T10:00:00")
        self.assertEqual(provider_reset.reset_at("429; resets at 14:00 UTC", base),
                         moment("2026-11-18T14:00:00"))

    def test_a_reset_at_the_moment_of_the_failure_stays_on_that_day(self):
        base = moment("2026-11-18T14:00:00")
        self.assertEqual(provider_reset.reset_at("429; resets at 14:00 UTC", base), base)

    def test_an_iso_reset_is_taken_as_it_is_written(self):
        base = moment("2026-11-18T10:00:00")
        self.assertEqual(
            provider_reset.reset_at("usage limit; resets at 2026-11-18T14:00:00Z", base),
            moment("2026-11-18T14:00:00"))

    def test_an_iso_reset_keeps_its_fractional_second(self):
        base = moment("2026-11-18T10:00:00")
        self.assertEqual(
            provider_reset.reset_at("usage limit; resets at 2026-11-18T14:00:00.500Z", base),
            moment("2026-11-18T14:00:00") + 0.5)

    def test_an_iso_reset_keeps_its_offset(self):
        base = moment("2026-11-18T10:00:00")
        self.assertEqual(
            provider_reset.reset_at("usage limit; resets at 2026-11-18T14:00:00.500+02:00", base),
            moment("2026-11-18T12:00:00") + 0.5)

    def test_a_time_of_day_reset_keeps_its_fractional_second(self):
        base = moment("2026-11-18T10:00:00")
        self.assertEqual(
            provider_reset.reset_at("usage limit; resets at 14:00:00.500 UTC", base),
            moment("2026-11-18T14:00:00") + 0.5)

    def test_the_glm_reset_is_read_in_the_zone_it_states(self):
        base = moment("2026-11-18T02:00:00")
        self.assertEqual(
            provider_reset.reset_at(
                "quota exhausted, will reset at 2026-11-18 11:58:52 (Asia/Shanghai)", base),
            moment("2026-11-18T03:58:52"))

    def test_a_reset_without_a_zone_is_read_as_utc(self):
        base = moment("2026-11-18T02:00:00")
        self.assertEqual(provider_reset.reset_at("will reset at 2026-11-18 11:58:52", base),
                         moment("2026-11-18T11:58:52"))

    def test_a_hyphenated_zone_name_is_read_whole(self):
        base = moment("2026-11-18T10:00:00")
        self.assertEqual(
            provider_reset.reset_at(
                "quota exhausted, will reset at 2026-11-18 11:58:52 America/Port-au-Prince", base),
            moment("2026-11-18T16:58:52"))

    def test_a_zone_name_that_says_gmt_is_read_before_a_bare_gmt(self):
        base = moment("2026-11-18T10:00:00")
        self.assertEqual(provider_reset.reset_at("usage limit; resets at 14:00 Etc/GMT+5", base),
                         moment("2026-11-18T19:00:00"))
        self.assertEqual(provider_reset.reset_at("usage limit; resets at 14:00 GMT", base),
                         moment("2026-11-18T14:00:00"))

    def test_an_offset_wins_over_a_bare_utc(self):
        base = moment("2026-11-18T10:00:00")
        self.assertEqual(
            provider_reset.reset_at("usage limit; resets at 2026-11-18 14:00:00 (UTC+08:00)", base),
            moment("2026-11-18T06:00:00"))

    def test_an_offset_a_clock_cannot_hold_is_no_zone(self):
        base = moment("2026-11-18T10:00:00")
        self.assertEqual(
            provider_reset.reset_at("usage limit; resets at 2026-11-18 14:00:00 (UTC+24:00)", base),
            moment("2026-11-18T14:00:00"))

    def test_a_reset_past_the_end_of_the_calendar_is_no_reset(self):
        base = moment("2026-11-18T10:00:00")
        self.assertIsNone(provider_reset.reset_at("429; retry after 999999999 hours", base))

    def test_a_reset_beyond_a_year_that_a_clock_can_hold_is_kept(self):
        base = moment("2026-11-18T10:00:00")
        self.assertEqual(provider_reset.reset_at("429; retry after 8800 hours", base),
                         moment("2027-11-20T02:00:00"))

    def test_a_next_day_reset_keeps_the_local_day_across_a_clock_change(self):
        base = moment("2026-11-01T06:00:00")
        self.assertEqual(
            provider_reset.reset_at("429; resets at 14:00 America/Los_Angeles", base),
            moment("2026-11-01T22:00:00"))

    def test_a_dated_reset_on_the_repeated_autumn_hour_is_read_on_its_second_pass(self):
        """At 01:15 PST on the day the clock goes back, the 01:30 that is
        still 15 minutes away is the one the message means."""
        base = moment("2026-11-01T09:15:00")
        self.assertEqual(
            provider_reset.reset_at(
                "quota exhausted, will reset at 2026-11-01 01:30:00 America/Los_Angeles", base),
            moment("2026-11-01T09:30:00"))

    def test_a_time_of_day_reset_on_the_repeated_autumn_hour_is_read_on_its_second_pass(self):
        base = moment("2026-11-01T09:15:00")
        self.assertEqual(provider_reset.reset_at("429; resets at 01:30 America/Los_Angeles", base),
                         moment("2026-11-01T09:30:00"))

    def test_a_message_with_no_reset_names_none(self):
        base = moment("2026-11-18T10:00:00")
        self.assertIsNone(provider_reset.reset_at("worker 14031 exited", base))
        self.assertIsNone(provider_reset.reset_at("", base))


if __name__ == "__main__":
    unittest.main()
