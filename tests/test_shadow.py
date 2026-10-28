"""Shadow verdict JSON extraction."""

from __future__ import annotations

import unittest

from reviewer_audit.shadow import _parse_verdict


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


if __name__ == "__main__":
    unittest.main()
