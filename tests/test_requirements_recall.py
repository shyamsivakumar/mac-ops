"""Requirement ID mapping for defect recall."""

from __future__ import annotations

import unittest

from reviewer_audit.requirements import requirement_ids_for_subject


class TestSrw61RecallSubjects(unittest.TestCase):
    def test_spx_level_track_phrasing(self):
        s = (
            "F1 — Requirement 4 (track underlying levels on SPX) is unmet on the "
            "documented live path."
        )
        self.assertIn("REQ-SPX-LEVEL-TRACK", requirement_ids_for_subject(s))

    def test_api_evidence_phrasing(self):
        s = "Requirement 1's exact API responses are missing from the saved evidence."
        self.assertIn("REQ-API-EVIDENCE", requirement_ids_for_subject(s))


if __name__ == "__main__":
    unittest.main()
