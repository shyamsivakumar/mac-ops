"""Shadow verdict JSON extraction."""

from __future__ import annotations

import unittest

from reviewer_audit.rescore import verdict_from_raw_entry
from reviewer_audit.shadow import _extract_json_verdict, _parse_verdict


class TestParseVerdict(unittest.TestCase):
    def test_first_line_json_with_codex_banner(self):
        raw = (
            '{"pass":true,"findings":[]}\n'
            "Reading additional input from stdin...\n"
            "OpenAI Codex v0.165.0\n"
        )
        v = _parse_verdict(raw, "gpt-6.1", 1)
        self.assertFalse(v.error)
        self.assertTrue(v.pass_verdict)

    def test_nested_finding_object_is_not_verdict(self):
        raw = '{ "pass":false, "findings":[ {"severity":"major","subject":"first finding"} '
        self.assertIsNone(_extract_json_verdict(raw))
        v = _parse_verdict(raw, "m", 1)
        self.assertTrue(v.error)

    def test_pass_false_without_findings_array_is_incomplete_for_rescore(self):
        entry = {
            "pass": False,
            "error": False,
            "subjects": [],
            "raw": '{"pass":false}',
        }
        v = verdict_from_raw_entry(entry, model="m", repeat=1)
        self.assertTrue(v.error)


if __name__ == "__main__":
    unittest.main()
