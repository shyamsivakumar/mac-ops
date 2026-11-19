"""The provider block store: the formats the providers answered with on
2026-11-17 and 2026-11-18, and the expiry of a block.

A block runs from the moment the run failed to the reset that text names,
and an entry whose reset has passed is no block.
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "coordinator" / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import models

SELECTION = {"instanceId": "glm", "model": "zai/glm-5.3"}
IDENTITY = "glm:glm-5.3"


def moment(text):
    """An ISO UTC moment as epoch seconds."""
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


class ProviderBlockTest(unittest.TestCase):
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

    def test_the_error_formats_of_2026_11_17_and_18_hold_the_provider_until_their_reset(self):
        """The formats the providers answered with, and the reset each names.

        The run failed at 02:00 UTC, so every reset the table names is still
        ahead of the failure."""
        failed = moment("2026-11-18T02:00:00")
        table = [
            # OpenAI, Anthropic and MiniMax named no reset, so an hour.
            ("You have no credits remaining", failed + 3600),
            ("credit balance is too low", failed + 3600),
            ("usage limit (429, code 2056)", failed + 3600),
            # A relative reset in minutes, then one in seconds.
            ("429 rate limit; resets in 30 minutes", failed + 1800),
            ("429: Too many requests. Please try in 30 seconds", failed + 30),
            # An absolute reset in UTC.
            ("429; resets at 14:00 UTC", moment("2026-11-18T14:00:00")),
            # The GLM format, in the zone its message states.
            ("quota exhausted, will reset at 2026-11-18 11:58:52 (Asia/Shanghai)",
             moment("2026-11-18T03:58:52")),
            # The GLM format with no zone stated is read as UTC.
            ("will reset at 2026-11-18 11:58:52", moment("2026-11-18T11:58:52")),
        ]
        for error, until in table:
            with self.subTest(error=error):
                self.assertEqual(models.reset_at(error, failed), until)

    def test_an_error_that_is_not_a_provider_refusal_blocks_nobody(self):
        """A local error is not the provider: it names no refusal, so it
        blocks nobody and the store stays empty."""
        for error in ["worker 14031 exited", "disk quota exceeded", "SyntaxError in coordq",
                      "FileNotFoundError: authentication.json", "429 count was 4290 items"]:
            with self.subTest(error=error):
                self.assertFalse(models.block_provider(SELECTION, error))
        self.assertEqual(models.read_blocked(), {})

    def test_a_block_is_held_until_its_reset_and_expires_after_it(self):
        failed = moment("2026-11-18T10:00:00")
        self.assertTrue(models.block_provider(SELECTION, "429 rate limit; resets in 30 minutes",
                                              failed=failed))
        stored = models.read_blocked()[IDENTITY]
        self.assertEqual((stored["failed"], stored["until"]), (failed, failed + 1800))
        self.assertEqual(models.blocked_identities(failed + 1799), {IDENTITY})
        self.assertEqual(models.blocked_identities(failed + 1801), set())

    def test_a_reset_that_has_passed_rolls_to_the_next_local_day(self):
        """At noon in New York on the day the clock goes back, a reset at
        09:00 is the 09:00 of the next day, an hour later in UTC than the
        same clock time on the day before."""
        failed = moment("2026-10-31T16:00:00")
        self.assertEqual(models.reset_at("resets at 09:00 America/New_York", failed),
                         moment("2026-11-01T14:00:00"))


if __name__ == "__main__":
    unittest.main()
