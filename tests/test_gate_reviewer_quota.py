"""Tests for the reviewer a gate falls back to after a quota failure.

Astra reviews every gate. When an Astra gate dies on a quota or a rate
limit, the next gate for that head runs once on Opus, and a head that has
tried every reviewer is queued no more.
"""
import argparse
import io
import json
import runpy
import tempfile
import unittest
from contextlib import redirect_stdout
from importlib.machinery import SourceFileLoader
from unittest.mock import patch

C = runpy.run_path('coordinator/bin/coordq')

ASTRA = C['ASTRA_MODEL']
OPUS = C['OPUS_MODEL']


class ReviewerQuotaTests(unittest.TestCase):
    def test_the_failover_is_astra_then_opus_and_then_nothing(self):
        queue = {}
        next_model = C['fallback_reviewer'](queue, 'head', ASTRA)
        self.assertEqual(next_model, OPUS)
        self.assertIsNone(C['fallback_reviewer'](queue, 'head', next_model))

    def test_an_opus_failure_leaves_no_reviewer(self):
        queue = {'gateReviewers': {'head': ['gpt-6-astra', 'claude-opus-5-5']}}
        self.assertIsNone(C['fallback_reviewer'](queue, 'head', OPUS))

    def test_quota_markers(self):
        for error in ['Spend limit', 'usage limit', 'rate_limit', 'HTTP 429']:
            self.assertTrue(C['quota_failure'](error))
        self.assertFalse(C['quota_failure']('syntax error'))


class GatekeepQuotaFallbackTest(unittest.TestCase):
    """One gate for a head that died on quota is re-queued on Opus, once."""

    key = 'gate:o/r#1:abc'

    def gatekeep(self, queue, thread_model, text, repeat=1):
        """Run one gatekeep pass against a queue this test owns."""
        c = SourceFileLoader('quota_coordq', 'coordinator/bin/coordq').load_module()
        args = {'modelSelection': c.ASTRA_MODEL, 'clientRequestId': self.key, 'title': 'gate'}
        event = {'kind': 'candidate', 'pr': 'o/r#1', 'head': 'abc', 'key': self.key,
                 'args': args}
        receipts = {self.key: 'gate-1'}
        dead = json.dumps({'thread': {'status': 'failed', 'model': thread_model,
                                      'providerInstanceId': 'codex'},
                           'items': [{'type': 'assistant_message', 'text': text}]})

        class Lock:
            def __init__(self, *a): pass
            def __enter__(self): pass
            def __exit__(self, *a): pass

        with tempfile.TemporaryDirectory() as d:
            config = d + '/config.json'
            with open(config, 'w') as f:
                json.dump({}, f)
            with patch.multiple(c, Lock=Lock, load=lambda: queue, save=lambda q: None,
                                load_counts=lambda: {}, write_counts=lambda *a: None,
                                gate_candidates=lambda cfg: [event] * repeat,
                                load_receipts=lambda: receipts,
                                path=lambda name: d + '/' + name,
                                call=lambda *a: (0, dead)):
                with redirect_stdout(io.StringIO()):
                    c.cmd_gatekeep(argparse.Namespace(config=config, dry_run=False))
        return queue

    def test_an_astra_quota_failure_is_requeued_once_on_opus(self):
        queue = {'gatedHeads': {self.key: 1}, 'items': [], 'next': 2}
        self.gatekeep(queue, 'gpt-6-astra', 'usage limit')
        self.assertEqual(len(queue['items']), 1)
        self.assertEqual(queue['items'][0]['args']['modelSelection'], OPUS)
        self.assertEqual(queue['items'][0]['args']['clientRequestId'],
                         self.key + ':claude-opus-5-5')

    def test_the_same_head_is_not_queued_twice(self):
        queue = {'gatedHeads': {self.key: 1}, 'items': [], 'next': 2}
        # The same head reaches the loop twice, so the run must queue one
        # reviewer, not two.
        self.gatekeep(queue, 'gpt-6-astra', 'spend limit', repeat=2)
        self.assertEqual(len(queue['items']), 1)

    def test_an_opus_failure_is_not_requeued(self):
        queue = {'gatedHeads': {self.key: {'id': 1, 'retries': 0, 'at': None, 'givenUp': False}},
                 'gateReviewers': {self.key: ['gpt-6-astra', 'claude-opus-5-5']},
                 'items': [], 'next': 2}
        self.gatekeep(queue, 'claude-opus-5-5', 'usage limit')
        self.assertEqual(queue['items'], [])


if __name__ == "__main__":
    unittest.main()
