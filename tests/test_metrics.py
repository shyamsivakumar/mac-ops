"""Metric definitions for reviewer audit."""

from __future__ import annotations

import unittest

from reviewer_audit.metrics import ShadowVerdict, compute_bundle_metrics


def _v(pass_verdict: bool, *, error: bool = False) -> ShadowVerdict:
    return ShadowVerdict(
        pass_verdict=pass_verdict,
        finding_subjects=[],
        requirement_ids=[],
        model="m",
        repeat=1,
        error=error,
    )


class TestFlipMetrics(unittest.TestCase):
    def test_pairwise_flip_rate_mixed_last(self):
        verdicts = [
            _v(True, error=False),
            _v(True),
            _v(True),
            _v(True),
            _v(False),
        ]
        for i, v in enumerate(verdicts):
            v.repeat = i + 1
        bm = compute_bundle_metrics(
            "x",
            verdicts,
            expected_pass=True,
            adjudicated_req_ids=[],
            saved_requirement_ids=[],
        )
        self.assertAlmostEqual(bm.flip_rate, 4 / 10)
        self.assertEqual(bm.adjacent_flip_count, 1)

    def test_all_errors_incomplete_no_false_block(self):
        verdicts = [_v(False, error=True) for _ in range(5)]
        for i, v in enumerate(verdicts):
            v.repeat = i + 1
        bm = compute_bundle_metrics(
            "x",
            verdicts,
            expected_pass=True,
            adjudicated_req_ids=[],
            saved_requirement_ids=[],
        )
        self.assertTrue(bm.incomplete)
        self.assertEqual(bm.valid_repeats, 0)
        self.assertIsNone(bm.flip_rate)
        self.assertIsNone(bm.false_block)


if __name__ == "__main__":
    unittest.main()
