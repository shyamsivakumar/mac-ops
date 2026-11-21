"""Per-host memory headroom tests cover the host floor and governor recovery."""
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import board_governor
import heavy


M1 = "shyams-macbook-pro"
M1_HEADROOM = 2 * heavy.GIB
DEFAULT = 6 * heavy.GIB


def sample(physical_gib, headroom_gib, captured=700.0):
    return heavy.Sample(
        pressure_level=1, cpu_busy_pct=10.0, memory_used_pct=50.0,
        headroom_bytes=int(headroom_gib * heavy.GIB),
        physical_bytes=int(physical_gib * heavy.GIB),
        load_per_core=0.2, captured_monotonic=captured, free_percent=60.0,
        swap_growth_bytes_per_second=0, swapout_bytes_per_second=0, physical_cores=10,
    )


class HostHeadroomTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def config(self, value):
        path = Path(self.directory.name) / heavy.CONFIG_NAME
        path.write_text(value if isinstance(value, str) else json.dumps(value))
        return path

    def floor_for(self, path, hostname):
        with patch.object(heavy.socket, "gethostname", return_value=hostname):
            return heavy.host_headroom_bytes(path)

    def test_a_named_host_gets_its_own_floor(self):
        path = self.config({heavy.HOST_HEADROOM_KEY: {M1: M1_HEADROOM}})
        self.assertEqual(self.floor_for(path, "Shyams-MacBook-Pro.local"), M1_HEADROOM)

    def test_a_mixed_case_configured_name_matches_the_hostname(self):
        path = self.config({heavy.HOST_HEADROOM_KEY: {"Shyams-MacBook-Pro.local": M1_HEADROOM}})
        self.assertEqual(self.floor_for(path, "Shyams-MacBook-Pro.local"), M1_HEADROOM)
        self.assertEqual(self.floor_for(path, "shyams-macbook-pro.local"), M1_HEADROOM)
        self.assertEqual(self.floor_for(path, "shyams-macbook-pro"), M1_HEADROOM)

    def test_a_mixed_case_short_name_matches_the_hostname(self):
        path = self.config({heavy.HOST_HEADROOM_KEY: {"Shyams-MacBook-Pro": M1_HEADROOM}})
        self.assertEqual(self.floor_for(path, "shyams-macbook-pro"), M1_HEADROOM)
        self.assertEqual(self.floor_for(path, "shyams-macbook-pro.local"), M1_HEADROOM)

    def test_conflicting_case_variants_keep_the_default_floor(self):
        path = self.config(
            {heavy.HOST_HEADROOM_KEY: {
                "Shyams-MacBook-Pro.local": M1_HEADROOM,
                "shyams-macbook-pro.local": 4 * heavy.GIB,
            }}
        )
        self.assertEqual(self.floor_for(path, "shyams-macbook-pro.local"), DEFAULT)
        self.assertEqual(self.floor_for(path, "Shyams-MacBook-Pro.local"), DEFAULT)

    def test_an_unlisted_host_keeps_the_default_floor(self):
        path = self.config({heavy.HOST_HEADROOM_KEY: {M1: M1_HEADROOM}})
        self.assertEqual(self.floor_for(path, "Shyams-M4.local"), DEFAULT)

    def test_a_qualified_name_does_not_lower_another_qualified_host(self):
        path = self.config({heavy.HOST_HEADROOM_KEY: {"builder.lab": M1_HEADROOM}})
        self.assertEqual(self.floor_for(path, "builder.office"), DEFAULT)
        self.assertEqual(self.floor_for(path, "builder.lab.office"), DEFAULT)
        self.assertEqual(self.floor_for(path, "builder.lab"), M1_HEADROOM)

    def test_an_unqualified_configured_name_matches_a_qualified_host(self):
        path = self.config({heavy.HOST_HEADROOM_KEY: {"builder": M1_HEADROOM}})
        self.assertEqual(self.floor_for(path, "builder.office"), M1_HEADROOM)

    def test_a_qualified_name_matches_an_unqualified_host(self):
        path = self.config({heavy.HOST_HEADROOM_KEY: {"builder.lab": M1_HEADROOM}})
        self.assertEqual(self.floor_for(path, "builder"), M1_HEADROOM)

    def test_two_qualified_names_sharing_a_short_name_are_ambiguous(self):
        path = self.config(
            {heavy.HOST_HEADROOM_KEY: {
                "builder.lab": M1_HEADROOM,
                "builder.office": 4 * heavy.GIB,
            }}
        )
        self.assertEqual(self.floor_for(path, "builder"), DEFAULT)
        self.assertEqual(self.floor_for(path, "builder.lab"), M1_HEADROOM)

    def test_a_missing_malformed_or_out_of_range_file_keeps_the_default_floor(self):
        absent = Path(self.directory.name) / "absent.json"
        self.assertEqual(heavy.host_headroom_bytes(absent), DEFAULT)
        self.assertEqual(self.floor_for(self.config("{not json"), M1), DEFAULT)
        path = self.config({heavy.HOST_HEADROOM_KEY: {M1: 0}})
        self.assertEqual(self.floor_for(path, M1), DEFAULT)
        path = self.config({heavy.HOST_HEADROOM_KEY: {M1: 65 * heavy.GIB}})
        self.assertEqual(self.floor_for(path, M1), DEFAULT)

    def test_a_symlinked_file_keeps_the_default_floor(self):
        target = self.config({heavy.HOST_HEADROOM_KEY: {M1: M1_HEADROOM}})
        link = Path(self.directory.name) / "link.json"
        link.symlink_to(target)
        self.assertEqual(self.floor_for(link, M1), DEFAULT)

    def test_a_shared_writable_file_keeps_the_default_floor(self):
        path = self.config({heavy.HOST_HEADROOM_KEY: {M1: M1_HEADROOM}})
        os.chmod(path, 0o666)
        self.assertEqual(self.floor_for(path, M1), DEFAULT)

    def test_a_pipe_keeps_the_default_floor_without_blocking(self):
        pipe = Path(self.directory.name) / "pipe.json"
        os.mkfifo(pipe)
        found = {}

        def look_up():
            found["floor"] = self.floor_for(pipe, M1)

        worker = threading.Thread(target=look_up, daemon=True)
        worker.start()
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive(), "the floor lookup blocked on a pipe")
        self.assertEqual(found.get("floor"), DEFAULT)

    def test_a_deeply_nested_file_keeps_the_default_floor(self):
        depth = sys.getrecursionlimit() + 1000
        nested = "[" * depth + "]" * depth
        self.assertLess(len(nested), 4096)
        if sys.version_info < (3, 12):
            with self.assertRaises(RecursionError):
                json.loads(nested)
        path = self.config(nested)
        self.assertEqual(self.floor_for(path, M1), DEFAULT)

    def test_a_parse_recursion_error_keeps_the_default_floor(self):
        path = self.config({heavy.HOST_HEADROOM_KEY: {M1: M1_HEADROOM}})
        with patch.object(heavy.json, "loads", side_effect=RecursionError):
            self.assertEqual(self.floor_for(path, M1), DEFAULT)

    def test_the_shipped_config_lowers_only_the_macbook_pro(self):
        value = json.loads((Path(heavy.__file__).parent / heavy.CONFIG_NAME).read_text())
        hosts = value[heavy.HOST_HEADROOM_KEY]
        self.assertEqual(hosts[M1], M1_HEADROOM)
        self.assertNotIn("shyams-m4", hosts)
        self.assertEqual(heavy.MIN_HEADROOM_BYTES, DEFAULT)

    def test_the_governor_config_accepts_the_host_map(self):
        path = Path(board_governor.__file__).parent / board_governor.DEFAULTS.name
        cfg = board_governor.config(path)
        self.assertEqual(cfg[board_governor.HOST_HEADROOM_KEY][M1], M1_HEADROOM)

    def test_the_governor_config_rejects_conflicting_case_variants(self):
        path = Path(board_governor.__file__).parent / board_governor.DEFAULTS.name
        values = json.loads(path.read_text())
        values[board_governor.HOST_HEADROOM_KEY] = {
            "Shyams-MacBook-Pro.local": M1_HEADROOM,
            "shyams-macbook-pro.local": M1_HEADROOM,
        }
        broken = Path(self.directory.name) / "governor.json"
        broken.write_text(json.dumps(values))
        with self.assertRaises(ValueError):
            board_governor.config(broken)

    def test_the_governor_config_rejects_a_fractional_headroom(self):
        path = Path(board_governor.__file__).parent / board_governor.DEFAULTS.name
        values = json.loads(path.read_text())
        values[board_governor.HOST_HEADROOM_KEY] = {M1: float(M1_HEADROOM)}
        broken = Path(self.directory.name) / "governor.json"
        broken.write_text(json.dumps(values))
        with self.assertRaises(ValueError):
            board_governor.config(broken)


class HeadroomFloorTests(unittest.TestCase):
    def block(self, headroom, floor):
        return heavy.memory_load_block_reason(
            pressure=1, free_percent=60.0, swap_growth=0, swapout_rate=0,
            headroom=headroom, physical=16 * heavy.GIB, min_headroom_bytes=floor,
        )

    def test_the_host_floor_admits_a_build_the_m1_cannot_fit_under_six_gibibytes(self):
        self.assertIsNone(self.block(3 * heavy.GIB, M1_HEADROOM))

    def test_the_default_floor_still_blocks_the_same_headroom(self):
        self.assertEqual(self.block(3 * heavy.GIB, DEFAULT), "memory-headroom")

    def test_the_slot_ceiling_is_unchanged(self):
        registry = Mock()
        registry.uid = 501
        registry.directory = Path("/nonexistent-heavy-test")
        with patch.object(heavy, "_read_capacity_config", return_value={"heavy_slots": 8}):
            limit = heavy._effective_slot_limit(registry, sample(16, 5), now=700.0, boot_id="1")
        self.assertEqual(limit, 2)


class GovernorRecoveryTests(unittest.TestCase):
    def decide(self, current, host_sample):
        previous = {
            "schema": 1, "boot_id": "1", "heavy_slots": current,
            "healthy_since_monotonic": None, "last_sample_monotonic": 690.0,
            "machine": [10, 16 * heavy.GIB], "compressor_bytes": 0,
            "compressor_sampled_monotonic": 680.0,
        }
        census = {"active": 0, "registry_active": 0, "legacy_active": 0, "job_rss_bytes": []}
        return board_governor._capacity_decision(
            heavy, host_sample, census, {"compressor_bytes": 0, "sampled_monotonic": 0.0},
            previous, current, "1", 700.0,
        )

    def test_the_governor_recovers_from_zero_on_its_next_sample(self):
        published = []
        for host_sample in (sample(16, 5, captured=600.0), sample(16, 5)):
            state, detail = self.decide(published[-1] if published else 0, host_sample)
            published.append(detail["target"])
        self.assertEqual(published, [0, 2])


if __name__ == "__main__":
    unittest.main()
