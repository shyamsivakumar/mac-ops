"""Rescore must not invent passes on unparseable raw."""

from __future__ import annotations

import unittest

from reviewer_audit.rescore import verdict_from_raw_entry


class TestRescoreVerdict(unittest.TestCase):
    def test_unparseable_raw_stays_error(self):
        entry = {
            "pass": False,
            "error": False,
            "subjects": ["some finding"],
            "requirement_ids": [],
            "raw": "not-json-at-all",
        }
        v = verdict_from_raw_entry(entry, model="m", repeat=1)
        self.assertTrue(v.error)
        self.assertFalse(v.pass_verdict)


if __name__ == "__main__":
    unittest.main()
