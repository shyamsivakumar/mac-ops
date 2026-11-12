"""Regression coverage for per-run model attribution from T3 run records."""
import tempfile
import unittest
from pathlib import Path

from session_traces.collect import collect_runs
from tests.test_session_traces import (
    REQUESTED_MODEL, TASK_MODEL, TASK_RUN_1, TASK_RUN_2, TASK_THREAD_ID, WINDOW_SINCE, WINDOW_UNTIL,
    _build_hub, _run,
)


class FallbackAttributionTests(unittest.TestCase):
    def collect(self, hub):
        return {t['run_id']: t for t in collect_runs(since=WINDOW_SINCE, until=WINDOW_UNTIL, t3_call=hub) if t['thread_id'] == TASK_THREAD_ID}

    def test_executed_model_different_from_requested_is_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub = _build_hub(Path(tmp), runs=[_run(TASK_RUN_1, model=REQUESTED_MODEL, executed_model=TASK_MODEL)], review=False)
            trace = self.collect(hub)[TASK_RUN_1]
            self.assertTrue(trace['model_fallback'])
            self.assertEqual(trace['requested_model'], REQUESTED_MODEL)
            self.assertEqual(trace['model'], TASK_MODEL)

    def test_same_executed_model_is_not_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub = _build_hub(Path(tmp), runs=[_run(TASK_RUN_1)], review=False)
            trace = self.collect(hub)[TASK_RUN_1]
            self.assertFalse(trace['model_fallback'])
            self.assertIsNone(trace['fallback_model'])

    def test_each_run_keeps_its_own_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = [
                _run(TASK_RUN_1, model=REQUESTED_MODEL, executed_model=TASK_MODEL),
                _run(TASK_RUN_2, ordinal=2, started_at='2026-11-03T16:21:00.000Z', completed_at='2026-11-03T16:30:00.000Z', model=TASK_MODEL),
            ]
            traces = self.collect(_build_hub(Path(tmp), runs=runs, review=False))
            self.assertTrue(traces[TASK_RUN_1]['model_fallback'])
            self.assertFalse(traces[TASK_RUN_2]['model_fallback'])


if __name__ == '__main__':
    unittest.main()
