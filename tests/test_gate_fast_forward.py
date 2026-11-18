"""The gate brief no longer orders a merge.

No merge call pins both the base and the head, so the lane merges nothing and
writes one decisions item on a PASS. This file pins that: no merge command, no
fast-forward, no close in the brief for an ordinary repository.
"""
import unittest

from tests.test_gatekeep_backstop_reviewer import load_coordq

REPO = "shyamsivakumar/mac-ops"
ISSUE = 296
NUMBER = 297
HEAD = "a" * 40


class GateNoMergeTests(unittest.TestCase):
    def setUp(self):
        self.q = load_coordq()

    def message(self, **settings):
        return self.q.gate_args(settings, REPO, ISSUE, NUMBER, HEAD,
                                publisher=False, model={})["message"]

    def test_no_merge_command(self):
        message = self.message(key="MO", projectId="P")
        self.assertNotIn("--match-head-commit", message)
        self.assertNotIn("repos/%s/merges" % REPO, message)

    def test_no_fast_forward_and_no_close(self):
        message = self.message(key="MO", projectId="P")
        self.assertNotIn("fast-forward", message)
        self.assertNotIn("gh issue close", message)

    def test_the_lane_writes_the_ask(self):
        message = self.message(key="MO", projectId="P")
        self.assertIn("the lane writes one decisions item", message)
        self.assertIn("do not merge", message)

    def test_an_ascend_repository_stops_at_the_verdict(self):
        message = self.message(key="ASC", projectId="P", ascend=True)
        self.assertIn("Ascend repo: do not merge", message)
