"""Role reservation tests exercise admission without launching host workloads."""
import contextlib
import dataclasses
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import heavy


class ReviewSlotTests(unittest.TestCase):
    def setUp(self):
        self.active = []
        self.queues = []
        self.registry = Mock()
        self.registry.directory = Path('/nonexistent-heavy-test')
        self.registry.lock.side_effect = contextlib.nullcontext
        self.registry.records.side_effect = lambda: list(self.active)
        self.registry.create.side_effect = self.active.append
        self.registry.remove_queue.side_effect = lambda qid: self.queues.__setitem__(
            slice(None), [q for q in self.queues if q['queue_id'] != qid])
        self.registry._read_record.side_effect = lambda jid: next(
            r for r in self.active if r['job_id'] == jid)
        self.registry.update.side_effect = self.update
        self.deps = heavy.SupervisorDeps(
            monotonic_ns=lambda: 700_000_000_000, clock=lambda: 700,
            wall_clock=lambda: 700, boot_reader=lambda: 'boot',
            process_table_reader=lambda: {}, legacy_slots=lambda table: 0)
        self.sample = heavy.Sample(
            pressure_level=1, cpu_busy_pct=10, memory_used_pct=20,
            headroom_bytes=32 * heavy.GIB, physical_bytes=48 * heavy.GIB,
            load_per_core=0.1, captured_monotonic=700, free_percent=70,
            swap_growth_bytes_per_second=0, swapout_bytes_per_second=0,
            physical_cores=8)
        patches = {
            '_legacy_draining': False, '_prune_finished_locked': None,
            '_supervisor_identity': {'pid': os.getpid()},
            '_identity_matches': True, '_read_capacity_config': {'heavy_slots': 2},
            '_record_live': (True, True), '_signal_owned_group': True,
            '_log_event': None,
        }
        for name, value in patches.items():
            p = patch.object(heavy, name, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(heavy, '_prune_queue_records_locked',
                         side_effect=lambda *args: list(self.queues))
        p.start()
        self.addCleanup(p.stop)

    def update(self, jid, fn):
        row = next(r for r in self.active if r['job_id'] == jid)
        changed = fn(dict(row))
        if changed is not None:
            row.clear()
            row.update(changed)
        return changed

    def running(self, key, role='ordinary', state='running', created=1):
        row = dict(job_id=key, task_key=key, task_id=key, role=role,
                   state=state, created_ns=created,
                   supervisor={'boot_id': 'boot'}, workload={'pid': 100})
        self.active.append(row)
        return row

    def queue(self, key, role='ordinary', created=699_000_000_000):
        row = dict(queue_id=key, task_key=key, role=role,
                   created_ns=created, process={'pid': os.getpid()})
        self.queues.append(row)
        return row

    def reserve(self, key, role='ordinary', sample=None):
        return heavy._reserve_job(self.registry, key, key, 'test',
                                  sample or self.sample, self.deps,
                                  queue_id=key, role=role)

    def test_running_review_allows_only_one_ordinary(self):
        for role in ('review', 'deploy'):
            with self.subTest(role=role):
                self.active.clear()
                self.queues.clear()
                self.running('priority', role)
                self.queue('ordinary')
                self.assertIsNotNone(self.reserve('ordinary')[0])
                self.queue('third')
                self.assertIsNone(self.reserve('third')[0])

    def test_next_free_slot_goes_to_review_even_before_aged_ordinary(self):
        for role in ('review', 'deploy'):
            with self.subTest(role=role):
                self.active.clear()
                self.queues.clear()
                self.running('one')
                self.running('two')
                self.queue('old', created=1)
                self.queue('priority', role)
                self.assertIsNone(self.reserve('priority', role)[0])
                self.active.pop()
                self.assertIsNone(self.reserve('old')[0])
                self.assertIsNotNone(self.reserve('priority', role)[0])
                self.assertEqual(len(self.active), 2)
                self.assertIsNone(self.reserve('old')[0])

    def test_ordinary_uses_both_slots_without_priority_demand(self):
        self.running('one')
        self.queue('two')
        self.assertIsNotNone(self.reserve('two')[0])
        self.queue('three')
        self.assertIsNone(self.reserve('three')[0])
        self.assertEqual(len(self.active), 2)

    def test_priority_does_not_bypass_cpu_or_memory(self):
        for role in ('review', 'deploy'):
            for changes in ({'cpu_busy_pct': 100}, {'memory_used_pct': 100}):
                with self.subTest(role=role, changes=changes):
                    self.queues.clear()
                    self.queue('priority', role)
                    self.assertIsNone(self.reserve(
                        'priority', role, dataclasses.replace(self.sample, **changes))[0])
                    self.assertFalse(self.active)

    def test_priority_cannot_exceed_global_limit(self):
        self.running('one')
        self.running('two', 'review')
        self.queue('priority', 'deploy')
        self.assertIsNone(self.reserve('priority', 'deploy')[0])
        self.assertEqual(len(self.active), 2)

    def test_paused_ordinary_cannot_reclaim_reserved_slot(self):
        for role in ('review', 'deploy'):
            for queued in (False, True):
                with self.subTest(role=role, queued=queued):
                    self.active.clear()
                    self.queues.clear()
                    self.running('one')
                    paused = self.running('paused', state='paused')
                    paused['pause'] = {'status': 'paused'}
                    if queued:
                        self.queue('priority', role)
                    else:
                        self.running('priority', role)
                    self.assertFalse(heavy._resume_current(
                        self.registry, 'paused', paused['workload'], self.sample, self.deps))

    def test_paused_ordinary_resumes_without_priority_demand(self):
        self.running('one')
        paused = self.running('paused', state='paused')
        paused['pause'] = {'status': 'paused'}
        self.assertTrue(heavy._resume_current(
            self.registry, 'paused', paused['workload'], self.sample, self.deps))


    def test_pressure_pauses_newest_ordinary_before_review(self):
        for with_review in (False, True):
            with self.subTest(with_review=with_review):
                self.active.clear()
                self.running('old', created=1)
                expected = 'old'
                if with_review:
                    self.running('review', 'review', created=3)
                else:
                    self.running('new', created=2)
                    expected = 'new'
                self.active.append({'job_id': heavy.PROTOCOL_RECORD_ID})
                self.assertEqual(heavy._request_global_pause(
                    self.registry, 'cpu-threshold', self.deps), expected)

    def test_reservation_never_opens_zero_capacity(self):
        self.queue('priority', 'review')
        with patch.object(heavy, '_read_capacity_config', return_value={'heavy_slots': 0}):
            self.assertIsNone(self.reserve('priority', 'review')[0])
        self.assertFalse(self.active)

    def test_limit_takeover_requires_the_claim_that_was_observed(self):
        workload = {'pid': 5, 'task_key': 'k', 'uid': 1, 'boot_id': 'b'}
        stale = {'reason': heavy.WALL_CLOCK_REASON, 'claimant_pid': 10, 'requested_ns': 1}
        self.active.append({
            'job_id': 'job', 'state': 'terminating', 'task_key': 'k', 'uid': 1,
            'supervisor': {'boot_id': 'b'}, 'workload': workload,
            'termination': dict(stale)})
        first = heavy._claim_termination(
            self.registry, 'job', heavy.WALL_CLOCK_REASON, claimant_pid=20,
            expected_workload=workload, takeover=True, observed_termination=stale)
        self.assertEqual(first['termination']['claimant_pid'], 20)
        second = heavy._claim_termination(
            self.registry, 'job', heavy.WALL_CLOCK_REASON, claimant_pid=30,
            expected_workload=workload, takeover=True, observed_termination=stale)
        self.assertIsNone(second)
        self.assertEqual(self.active[0]['termination']['claimant_pid'], 20)

    def test_watchdog_stale_recovery_defers_to_a_live_limit_claim(self):
        workload = {'pid': 5, 'task_key': 'k', 'uid': os.getuid(), 'boot_id': 'b'}
        now = 10_000_000_000_000
        claim = {'reason': heavy.WALL_CLOCK_REASON, 'claimant_pid': os.getppid(),
                 'requested_ns': now - 1_000_000_000}
        self.active.append({
            'job_id': 'job', 'state': 'terminating', 'task_key': 'k',
            'uid': os.getuid(), 'created_ns': 1, 'supervisor': {'boot_id': 'b'},
            'workload': workload, 'termination': dict(claim)})
        self.registry.lock.side_effect = lambda **_: contextlib.nullcontext()
        self.registry.read_heartbeat.return_value = None
        terminate = Mock(return_value=True)

        class Stop(Exception):
            pass

        def stop(_seconds):
            raise Stop

        with self.assertRaises(Stop):
            heavy.watchdog_loop(
                'job', self.registry, clock_ns=lambda: now, sleep=stop,
                table_reader=lambda: {}, boot_reader=lambda: 'b',
                terminate=terminate)
        terminate.assert_not_called()
        self.assertEqual(self.active[0]['termination'], claim)

    def test_watchdog_takeover_requires_the_observed_claim(self):
        workload = {'pid': 5}
        observed = {'claimant_pid': 1, 'requested_ns': 1}
        record = {'workload': workload,
                  'termination': {'claimant_pid': 2, 'requested_ns': 1}}
        self.assertIsNone(heavy._watchdog_takeover_record(record, workload, 3, observed))
        record['termination'] = dict(observed)
        self.assertEqual(heavy._watchdog_takeover_record(
            record, workload, 3, observed)['termination']['claimant_pid'], 3)


if __name__ == '__main__':
    unittest.main()
