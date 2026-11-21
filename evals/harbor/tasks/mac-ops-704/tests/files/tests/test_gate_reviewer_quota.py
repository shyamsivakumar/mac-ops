import os
import runpy
import tempfile
import unittest
from unittest.mock import patch

C = runpy.run_path('coordinator/bin/coordq')


def setUpModule():
    queue = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(queue.cleanup)
    environment = patch.dict(os.environ, {"COORDQ_DIR": queue.name})
    environment.start()
    unittest.addModuleCleanup(environment.stop)


def review_selection(entry_id):
    return next(e['selection'] for e in C['model_list'].entries('review') if e['id'] == entry_id)


class ReviewerQuotaTests(unittest.TestCase):
    def test_vendor_routing(self):
        for builder, expected in [('claude', 'astra-api'), ('gpt-6.1-sol', 'opus-api'), ('minimax/m3', 'astra-api'), ('deepseek/flash', 'astra-api'), ('glm/5', 'astra-api')]:
            self.assertEqual(C['reviewer_model']([builder]), review_selection(expected))
        self.assertEqual(C['reviewer_model']([]), review_selection('astra-api'))

    def test_quota_exhaustion_excludes_builder(self):
        queue = {}
        current = review_selection('astra-api')
        next_model = C['fallback_reviewer'](queue, 'head', current, ['gpt-6.1-sol'])
        self.assertEqual(next_model, review_selection('opus-api'))
        last_model = C['fallback_reviewer'](queue, 'head', next_model, ['gpt-6.1-sol'])
        self.assertEqual(last_model, review_selection('opus-sub'))
        self.assertIsNone(C['fallback_reviewer'](queue, 'head', last_model, ['gpt-6.1-sol']))

    def test_quota_markers(self):
        for error in ['Spend limit', 'usage limit', 'quota exhausted', 'insufficient_quota']:
            self.assertTrue(C['quota_failure']({'error': {'message': error}}))
        for error in ['syntax error', 'rate_limit', 'HTTP 429']:
            self.assertFalse(C['quota_failure']({'error': {'message': error}}))
        self.assertFalse(C['quota_failure']({'thread': {'status': 'interrupted'}, 'items': [{'text': 'quota exhausted'}]}))

    def test_failed_thread_queues_once(self):
        import tempfile
        import json
        import argparse
        from unittest.mock import patch
        from contextlib import redirect_stdout
        import io
        from importlib.machinery import SourceFileLoader
        c = SourceFileLoader('quota_coordq', 'coordinator/bin/coordq').load_module()
        key = 'gate:o/r#1:abc'
        args = {'modelSelection': review_selection('astra-api'), 'clientRequestId': key, 'title': 'gate'}
        event = {'kind': 'candidate', 'pr': 'o/r#1', 'head': 'abc', 'key': key, 'args': args, 'builderModels': ['minimax/m3']}
        queue = {'gatedHeads': {key: 1}, 'items': [], 'next': 2}
        class Lock:
            def __init__(self, *a): pass
            def __enter__(self): pass
            def __exit__(self, *a): pass
        with tempfile.TemporaryDirectory() as d:
            config = d + '/config.json'
            with open(config, 'w') as f: json.dump({}, f)
            receipts = {key: 'failed'}
            with patch.multiple(c, Lock=Lock, load=lambda: queue, save=lambda q: None,
                    load_counts=lambda: {}, write_counts=lambda *a: None,
                    # The same head reaches the loop twice, so the run must
                    # queue one reviewer, not two.
                    gate_candidates=lambda cfg, rounds=None: [event, event], load_receipts=lambda: receipts,
                    path=lambda name: d + '/' + name,
                    call=lambda *a: (0, json.dumps({'thread': {'status': 'failed', 'model': 'openai/gpt-6.2-astra', 'providerInstanceId': 'openai-api', 'error': {'code': 'insufficient_quota'}}, 'items': [{'type': 'assistant_message', 'text': 'spend limit'}]}))):
                with redirect_stdout(io.StringIO()):
                    c.cmd_gatekeep(argparse.Namespace(config=config, dry_run=False))
                    c.cmd_gatekeep(argparse.Namespace(config=config, dry_run=False))
            self.assertEqual(len(queue['items']), 1)
            self.assertEqual(queue['items'][0]['args']['modelSelection'], review_selection('astra-sub'))
