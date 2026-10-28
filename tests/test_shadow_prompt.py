"""Shadow prompt uses board ship-and-score instructions."""

from __future__ import annotations

import unittest

from reviewer_audit.bundles import ReviewBundle
from reviewer_audit.shadow import LEGACY_PASS_RULE, _shadow_prompt


def _minimal_bundle() -> ReviewBundle:
    return ReviewBundle(
        bundle_id="test--r1--abc",
        task_id="mac-ops/1",
        review_round=1,
        title="t",
        head="abc",
        diff_base="def",
        cohort="regression-clean",
        input_hash="h",
        stat="",
        diff_text="diff",
        saved_proof="proof",
        description="desc",
        description_excerpt="",
        agent_closing_note="",
        closing_note_excerpt="",
        saved_review_pass=True,
        saved_finding_subjects=[],
        saved_requirement_ids=[],
        expected_pass=True,
        adjudicated_defects=[],
    )


class TestShadowPrompt(unittest.TestCase):
    def test_board_policy_includes_ship_and_score(self):
        prompt = _shadow_prompt(_minimal_bundle(), review_policy="board")
        self.assertIn("reviewer.instructions (board mac-ops)", prompt)
        self.assertIn("Ship-and-score policy", prompt)
        self.assertNotIn(LEGACY_PASS_RULE, prompt)

    def test_legacy_policy_uses_major_gate(self):
        prompt = _shadow_prompt(_minimal_bundle(), review_policy="legacy")
        self.assertIn(LEGACY_PASS_RULE, prompt)
        self.assertNotIn("reviewer.instructions (board mac-ops)", prompt)


if __name__ == "__main__":
    unittest.main()
