"""Regression coverage for model changes and second-resolution routing logs."""
import json
import tempfile
import unittest
from pathlib import Path

from session_traces.collect import collect_runs
from tests.test_session_traces import (
    TASK_RUN_1, TASK_RUN_2, TASK_THREAD_ID, WINDOW_SINCE, WINDOW_UNTIL,
    _build_hub, _hub_stamp, _run,
)


class FallbackAttributionTests(unittest.TestCase):
    def collect(self, hub):
        return {t['run_id']: t for t in collect_runs(since=WINDOW_SINCE, until=WINDOW_UNTIL, hub_path=hub) if t['thread_id'] == TASK_THREAD_ID}

    def test_changed_thread_model_is_not_historical_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = [_run(TASK_RUN_1), _run(TASK_RUN_2, ordinal=2, started_at='2026-11-03T16:21:00.000Z', completed_at='2026-11-03T16:30:00.000Z', model='subscriptions/gpt-6.1-sol')]
            hub = _build_hub(Path(tmp), runs=runs, review=False)
            path = hub / 'threads.json'
            data = json.loads(path.read_text())
            data[TASK_THREAD_ID]['modelSelection']['model'] = 'subscriptions/gpt-6.1-sol'
            path.write_text(json.dumps(data))
            traces = self.collect(hub)
            self.assertFalse(traces[TASK_RUN_1]['model_fallback'])
            self.assertIsNone(traces[TASK_RUN_1]['requested_model'])
            self.assertFalse(traces[TASK_RUN_2]['model_fallback'])

    def test_latest_run_can_predate_model_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = [_run(TASK_RUN_1, model='subscriptions/gpt-6.1-sol'), _run(TASK_RUN_2, ordinal=2, started_at='2026-11-03T16:21:00.000Z', completed_at='2026-11-03T16:30:00.000Z', model='subscriptions/claude-opus-5-5')]
            hub = _build_hub(Path(tmp), runs=runs, review=False)
            path = hub / 'threads.json'
            data = json.loads(path.read_text())
            data[TASK_THREAD_ID]['modelSelection']['model'] = 'subscriptions/gpt-6.1-sol'
            path.write_text(json.dumps(data))
            trace = self.collect(hub)[TASK_RUN_2]
            self.assertFalse(trace['model_fallback'])
            self.assertIsNone(trace['requested_model'])

    def test_same_second_route_belongs_to_next_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = [_run(TASK_RUN_1, model='subscriptions/claude-opus-5-5', completed_at='2026-11-03T16:20:00.673Z'), _run(TASK_RUN_2, ordinal=2, started_at='2026-11-03T16:20:00.900Z', completed_at='2026-11-03T16:30:00.000Z')]
            line = f"{_hub_stamp('2026-11-03T16:20:00Z')} {TASK_THREAD_ID} routed to subscriptions/gpt-6.1-terra instead of anthropic/claude-opus-5-5 (circuit for anthropic is open)"
            hub = _build_hub(Path(tmp), runs=runs, review=False, extra_log=(line,))
            traces = self.collect(hub)
            self.assertFalse(traces[TASK_RUN_1]['model_fallback'])
            self.assertTrue(traces[TASK_RUN_2]['model_fallback'])
            self.assertEqual(traces[TASK_RUN_2]['base_model'], 'anthropic/claude-opus-5-5')


if __name__ == '__main__':
    unittest.main()
