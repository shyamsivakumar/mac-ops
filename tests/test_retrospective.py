"""Retrospective input hashing."""

from __future__ import annotations

import unittest

from reviewer_audit.bundles import resolve_review_base
from reviewer_audit.retrospective import review_input_hash


class TestRetrospectiveHash(unittest.TestCase):
    def test_same_head_different_rounds_share_hash(self):
        task = {
            "id": "catalogue/2",
            "description": "d",
            "reviews": [
                {"round": 1, "by": "codex", "head": "5d64ba2a5959054586efc3650cdb3fe8133e2346"},
                {"round": 2, "by": "codex", "head": "5d64ba2a5959054586efc3650cdb3fe8133e2346"},
            ],
        }
        closing = ""
        reviews = [
            r
            for r in task.get("reviews") or []
            if r.get("head") == "5d64ba2a5959054586efc3650cdb3fe8133e2346"
        ]
        self.assertGreaterEqual(len(reviews), 2)
        hashes = {review_input_hash(task, r, closing) for r in reviews[:2]}
        self.assertEqual(len(hashes), 1)

    def test_srw61_round1_base_from_checks(self):
        task = {
            "id": "strategy-replay-workbench/61",
            "reviews": [
                {
                    "round": 1,
                    "checks": [
                        "Reviewed the diff against base 87be8cadc07a1b2c3d4e5f60718293a4b5c6d7e8"
                    ],
                }
            ],
        }
        review = next(r for r in task["reviews"] if r["round"] == 1)
        base = resolve_review_base(task, review)
        self.assertTrue(base.startswith("87be8cadc07"))


if __name__ == "__main__":
    unittest.main()
