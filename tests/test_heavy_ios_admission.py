"""iOS build admission tests cover small hosts and simulator-backed jobs."""
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

    def test_a_telemetry_error_does_not_pin_the_governor_at_zero_slots(self):
        state, detail = self.decide(0, sample(16, 5, captured=600.0))
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
