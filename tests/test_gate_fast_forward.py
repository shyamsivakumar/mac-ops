"""Tests for the gate's post-merge fast-forward of local main.

The gate message is the whole script of a review gate, so the ordering
asserted here is the contract: merge, then fast-forward, then close, and
no fast-forward at all where the gate does not merge.
"""
import unittest

from tests.test_gatekeep_backstop_reviewer import load_coordq

REPO = "shyamsivakumar/fixture"
ISSUE = 296
NUMBER = 297
HEAD = "a" * 40

MERGE_END = "report the merge commit or refusal."
FAST_FORWARD = "fast-forward this repository's local main to origin/main"
FAST_FORWARD_GUARD = "Only when that merge produced a merge commit"
REFUSAL = "or the exact refusal"
NO_OTHER = "Fast-forward no other repository."
CLOSE = "close the ticket"


class GateFastForwardTests(unittest.TestCase):
    def setUp(self):
        self.q = load_coordq()

    def message(self, **settings):
        return self.q.gate_args(settings, REPO, ISSUE, NUMBER, HEAD,
                                publisher=False, model={})["message"]

    def test_fast_forward_immediately_follows_the_merge_step(self):
        message = self.message(key="MO", projectId="P")
        merge_end = message.index(MERGE_END) + len(MERGE_END)
        self.assertTrue(
            message[merge_end:].startswith(" " + FAST_FORWARD_GUARD + ", " + FAST_FORWARD),
            message[merge_end:merge_end + 160])

    def test_merge_step_carries_no_fast_forward(self):
        message = self.message(key="MO", projectId="P")
        merge_end = message.index(MERGE_END)
        self.assertNotIn("ff-only", message[:merge_end])
        self.assertNotIn("worktree list", message[:merge_end])

    def test_fast_forward_precedes_the_close_step(self):
        message = self.message(key="MO", projectId="P")
        self.assertLess(message.index(FAST_FORWARD), message.index(CLOSE))

    def test_fast_forward_reports_the_pair_or_the_refusal(self):
        message = self.message(key="MO", projectId="P")
        self.assertIn("git rev-parse main origin/main", message)
        self.assertIn(REFUSAL, message)
        self.assertIn("never force", message)
        self.assertIn(NO_OTHER, message)

    def test_checked_out_main_merges_and_absent_main_fetches_into_the_ref(self):
        message = self.message(key="MO", projectId="P")
        self.assertIn("git worktree list", message)
        self.assertIn("git merge --ff-only origin/main", message)
        self.assertIn("git fetch origin main:main", message)

    def test_ascend_setting_has_no_fast_forward(self):
        message = self.message(key="ASC", projectId="P", ascend=True)
        self.assertNotIn("fast-forward", message.lower())
        self.assertNotIn("ff-only", message)
        self.assertIn("do not merge", message)

    def test_ascend_org_has_no_fast_forward(self):
        message = self.q.gate_args({"key": "ASC", "projectId": "P"},
                                   "ascend-ops/hub", ISSUE, NUMBER, HEAD,
                                   publisher=False, model={})["message"]
        self.assertNotIn("fast-forward", message.lower())
        self.assertNotIn("ff-only", message)

    def test_ascend_repo_still_closes_nothing_and_merges_nothing(self):
        message = self.message(key="ASC", projectId="P", ascend=True)
        self.assertIn("do not close the issue", message)
        self.assertNotIn("gh pr merge", message)


if __name__ == "__main__":
    unittest.main()
