"""iOS build admission tests cover small hosts and simulator-backed jobs."""
import contextlib
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import board_governor
import heavy


def sample(physical_gib, headroom_gib, *, captured=700.0, cores=10):
    return heavy.Sample(
        pressure_level=1,
        cpu_busy_pct=10.0,
        memory_used_pct=50.0,
        headroom_bytes=int(headroom_gib * heavy.GIB),
        physical_bytes=int(physical_gib * heavy.GIB),
        load_per_core=0.2,
        captured_monotonic=captured,
        free_percent=60.0,
        swap_growth_bytes_per_second=0,
        swapout_bytes_per_second=0,
        physical_cores=cores,
    )


class SmallHostAdmissionTests(unittest.TestCase):
    def test_a_sixteen_gigabyte_host_admits_a_build_the_simulator_leaves_room_for(self):
        reason = heavy.admission_block_reason(
            sample(16, 5),
            now=700.0,
            active_count=0,
            task_already_active=False,
            slot_limit=2,
        )
        self.assertIsNone(reason)

    def test_a_large_host_still_needs_its_own_scaled_headroom(self):
        reason = heavy.admission_block_reason(
            sample(48, 7),
            now=700.0,
            active_count=0,
            task_already_active=False,
            slot_limit=2,
        )
        self.assertEqual(reason, "memory-headroom")

    def test_a_large_host_admits_a_job_with_the_old_headroom(self):
        reason = heavy.admission_block_reason(
            sample(48, 7.5),
            now=700.0,
            active_count=0,
            task_already_active=False,
            slot_limit=2,
        )
        self.assertIsNone(reason)

    def test_a_small_host_still_refuses_when_the_host_has_no_room(self):
        reason = heavy.admission_block_reason(
            sample(16, 1),
            now=700.0,
            active_count=0,
            task_already_active=False,
            slot_limit=2,
        )
        self.assertEqual(reason, "memory-headroom")

    def test_the_simulator_a_job_will_use_counts_as_part_of_that_job(self):
        reason = heavy.admission_block_reason(
            sample(16, 1),
            now=700.0,
            active_count=0,
            task_already_active=False,
            slot_limit=2,
            allowance_bytes=2 * heavy.GIB,
        )
        self.assertIsNone(reason)

    def test_the_simulator_credit_is_capped_at_an_eighth_of_the_host(self):
        reason = heavy.admission_block_reason(
            sample(16, 0.1),
            now=700.0,
            active_count=0,
            task_already_active=False,
            slot_limit=2,
            allowance_bytes=16 * heavy.GIB,
        )
        self.assertEqual(reason, "memory-headroom")

    def test_a_small_host_scales_its_headroom_with_its_memory(self):
        self.assertEqual(
            heavy.required_headroom_bytes(16 * heavy.GIB),
            int(16 * heavy.GIB * 0.15),
        )
        self.assertEqual(
            heavy.required_headroom_bytes(48 * heavy.GIB),
            int(48 * heavy.GIB * 0.15),
        )

    def test_a_large_host_keeps_the_old_max_of_six_gigabytes_and_a_share_of_ram(self):
        self.assertEqual(
            heavy.required_headroom_bytes(48 * heavy.GIB),
            max(6 * heavy.GIB, int(48 * heavy.GIB * 0.15)),
        )
        self.assertEqual(
            heavy.required_headroom_bytes(48 * heavy.GIB, 0.125),
            max(6 * heavy.GIB, int(48 * heavy.GIB * 0.125)),
        )

    def test_a_running_job_keeps_the_original_pause_threshold(self):
        reason = heavy._host_reason(sample(16, 3))
        self.assertEqual(reason, "memory-headroom-or-swap-pressure")

    def test_the_simulator_a_job_drives_is_credited_against_the_pause_threshold(self):
        reason = heavy._host_reason(sample(16, 4), allowance_bytes=2 * heavy.GIB)
        self.assertIsNone(reason)

    def test_a_large_host_pause_threshold_is_unchanged(self):
        self.assertEqual(
            heavy.pause_headroom_bytes(48 * heavy.GIB),
            max(6 * heavy.GIB, int(48 * heavy.GIB * 0.125)),
        )
        self.assertEqual(
            heavy.pause_headroom_bytes(16 * heavy.GIB),
            max(6 * heavy.GIB, int(16 * heavy.GIB * 0.125)),
        )

    def test_the_resume_threshold_keeps_the_old_share_of_ram(self):
        self.assertEqual(
            heavy.pause_headroom_bytes(48 * heavy.GIB, True),
            max(6 * heavy.GIB, int(48 * heavy.GIB * 0.15)),
        )
        reason = heavy._host_reason(sample(48, 7), paused=True)
        self.assertEqual(reason, "memory-headroom-or-swap-pressure")
        self.assertIsNone(heavy._host_reason(sample(48, 7.5), paused=True))

    def test_the_simulator_credit_does_not_relax_a_large_host(self):
        reason = heavy.admission_block_reason(
            sample(48, 7),
            now=700.0,
            active_count=0,
            task_already_active=False,
            slot_limit=2,
            allowance_bytes=4 * heavy.GIB,
        )
        self.assertEqual(reason, "memory-headroom")


class SimulatorCreditTests(unittest.TestCase):
    def test_only_an_xcodebuild_simulator_destination_claims_a_credit(self):
        self.assertIsNone(
            heavy.simulator_destination_device(["swift", "build"])
        )
        self.assertEqual(
            heavy.simulator_destination_device(
                ["xcodebuild", "-destination", "platform=iOS Simulator,name=CI-iPhone"]
            ),
            "CI-iPhone",
        )

    def test_a_command_without_a_booted_simulator_claims_no_credit(self):
        self.assertEqual(heavy.simulator_memory_credit_bytes(["swift", "build"]), 0)


class GovernorRecoveryTests(unittest.TestCase):
    def census(self):
        return {
            "active": 0,
            "registry_active": 0,
            "legacy_active": 0,
            "job_rss_bytes": [],
        }

    def compressor(self):
        return {"compressor_bytes": 0, "sampled_monotonic": 0.0}

    def decide(self, current, host_sample):
        return board_governor._capacity_decision(
            heavy,
            host_sample,
            self.census(),
            self.compressor(),
            {
                "schema": 1,
                "boot_id": "1",
                "heavy_slots": current,
                "healthy_since_monotonic": None,
                "last_sample_monotonic": 690.0,
                "machine": [10, 16 * heavy.GIB],
                "compressor_bytes": 0,
                "compressor_sampled_monotonic": 680.0,
            },
            current,
            "1",
            700.0,
        )

    def test_a_zero_slot_governor_recovers_on_its_next_sample(self):
        state, detail = self.decide(0, sample(16, 5))
        self.assertEqual(detail["target"], 2)
        self.assertEqual(state["heavy_slots"], 2)

    def test_an_unreadable_sample_holds_the_capacity_it_has(self):
        state, detail = self.decide(0, sample(16, 5, captured=600.0))
        self.assertEqual(detail["target"], 0)
        self.assertEqual(state["heavy_slots"], 0)

    def test_the_next_good_sample_restores_the_slots(self):
        state, detail = self.decide(0, sample(16, 5))
        self.assertEqual(detail["target"], 2)
        self.assertEqual(state["heavy_slots"], 2)


if __name__ == "__main__":
    unittest.main()


class SmallHostSlotTests(unittest.TestCase):
    def test_a_small_host_keeps_the_two_job_limit(self):
        registry = Mock()
        registry.uid = 501
        registry.directory = Path('/nonexistent-heavy-test')
        with patch.object(heavy, "_read_capacity_config", return_value={"heavy_slots": 2}):
            limit = heavy._effective_slot_limit(registry, sample(16, 5), now=700.0, boot_id="1")
        self.assertEqual(limit, 2)

    def test_a_large_host_keeps_its_slot_ceiling(self):
        registry = Mock()
        registry.uid = 501
        registry.directory = Path('/nonexistent-heavy-test')
        with patch.object(heavy, "_read_capacity_config", return_value={"heavy_slots": 2}):
            limit = heavy._effective_slot_limit(registry, sample(48, 30), now=700.0, boot_id="1")
        self.assertEqual(limit, 2)


class TelemetryGapTests(unittest.TestCase):
    def test_a_busy_cpu_sample_still_gives_a_reading(self):
        reading = heavy.parse_cpu_busy(
            "      cpu    load average\n"
            " us sy id   1m   5m   15m\n"
            " 23 13 64  20.81 23.02 26.55\n"
            " 49 30 21  20.90 23.00 26.52\n"
        )
        self.assertAlmostEqual(reading, 79.0)

    def test_an_inconsistent_cpu_sample_falls_back_to_the_idle_share(self):
        reading = heavy.parse_cpu_busy(
            "      cpu    load average\n"
            " us sy id   1m   5m   15m\n"
            " 23 13 64  20.81 23.02 26.55\n"
            " 60 30  2  20.90 23.00 26.52\n"
        )
        self.assertAlmostEqual(reading, 98.0)

    def test_a_missing_cpu_reading_still_counts_as_critical_pressure(self):
        gap = heavy.Sample(
            pressure_level=1, cpu_busy_pct=None, memory_used_pct=50.0,
            headroom_bytes=5 * heavy.GIB, physical_bytes=16 * heavy.GIB,
            load_per_core=3.0, captured_monotonic=700.0, free_percent=60.0,
            swap_growth_bytes_per_second=0, swapout_bytes_per_second=0,
            physical_cores=10)
        self.assertFalse(heavy.critical_pressure(gap, load_proxy=False))
        self.assertTrue(heavy.critical_pressure(gap))


class XcodebuildExclusionTests(unittest.TestCase):
    """One xcodebuild runs at a time, whatever the slot count says."""

    def setUp(self):
        self.active = []
        self.queues = []
        self.registry = Mock()
        self.registry.uid = 501
        self.registry.directory = Path('/nonexistent-heavy-test')
        self.registry.lock.side_effect = contextlib.nullcontext
        self.registry.records.side_effect = lambda: list(self.active)
        self.registry.create.side_effect = self.active.append
        self.registry.remove_queue.side_effect = lambda qid: self.queues.__setitem__(
            slice(None), [q for q in self.queues if q['queue_id'] != qid])
        self.registry.update.side_effect = self.update
        self.deps = heavy.SupervisorDeps(
            monotonic_ns=lambda: 700_000_000_000, clock=lambda: 700,
            wall_clock=lambda: 700, boot_reader=lambda: 'boot',
            process_table_reader=lambda: {}, legacy_slots=lambda table: 0)
        self.sample = sample(16, 5)
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

    def running(self, key, command='xcodebuild'):
        row = dict(job_id=key, task_key=key, task_id=key, role='ordinary',
                   command_basename=command, state='running', created_ns=1,
                   supervisor={'boot_id': 'boot'}, workload={'pid': 100})
        self.active.append(row)
        return row

    def queue(self, key):
        row = dict(queue_id=key, task_key=key, role='ordinary',
                   created_ns=699_000_000_000, process={'pid': os.getpid()})
        self.queues.append(row)
        return row

    def reserve(self, key, command='xcodebuild'):
        return heavy._reserve_job(self.registry, key, key, command,
                                  self.sample, self.deps, queue_id=key)

    def test_a_second_xcodebuild_waits_for_the_first(self):
        self.running('first')
        self.queue('second')
        job_id, reason = self.reserve('second')
        self.assertIsNone(job_id)
        self.assertEqual(reason, 'xcodebuild-busy')

    def test_a_large_host_keeps_its_build_concurrency(self):
        self.sample = sample(48, 30)
        self.running('first')
        self.queue('second')
        job_id, reason = self.reserve('second')
        self.assertIsNotNone(job_id)
        self.assertIsNone(reason)

    def test_another_workload_may_start_beside_a_build(self):
        self.running('first')
        self.queue('other')
        job_id, reason = self.reserve('other', command='check.sh')
        self.assertIsNotNone(job_id)
        self.assertIsNone(reason)

    def test_a_build_starts_when_no_build_runs(self):
        self.queue('only')
        job_id, reason = self.reserve('only')
        self.assertIsNotNone(job_id)
        self.assertIsNone(reason)
