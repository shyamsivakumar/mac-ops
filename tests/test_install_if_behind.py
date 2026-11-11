import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(os.environ.get("TMPDIR", tempfile.gettempdir()))

spec = importlib.util.spec_from_file_location(
    "install_if_behind", ROOT / "scripts" / "install_if_behind.py"
)
install_if_behind = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install_if_behind)


def _tick(updated_at, release, **extra):
    row = {
        "updated_at": updated_at,
        "runtime": str(release),
        "board": {
            "current": 14,
            "decision": {
                "target": 14,
                "active": 4,
                "host_veto": None,
                "reason": "await_capacity_headroom",
            },
        },
        "heavy_decision": {"target": 2, "reason": "baseline_floor_hold"},
    }
    row.update(extra)
    return row


def _write(state, rows):
    (state / "controller.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


class InstallObservationTests(unittest.TestCase):
    def setUp(self):
        TMP.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=TMP)
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        self.release = self.state / "release"
        self.release.mkdir()
        self._time = install_if_behind.time.time
        self._sleep = install_if_behind.time.sleep
        self.addCleanup(self._restore_clock)

    def _restore_clock(self):
        install_if_behind.time.time = self._time
        install_if_behind.time.sleep = self._sleep

    def test_census_process_exit_passes_and_controller_failure_rolls_back(self):
        started = 1_793_325_518.0
        exit_rows = [_tick(started + i * 5, self.release) for i in range(12)]
        exit_rows[4]["board_agent_census"] = {
            "schema": 1,
            "complete": False,
            "errors": [
                "strategy-replay-workbench/185: foreground process exited during collection"
            ],
        }
        passed = install_if_behind.evaluate_controller_ticks(
            exit_rows,
            target_release=self.release,
            install_started_at=started,
            min_ticks=12,
        )
        self.assertTrue(passed["passed"], passed)
        self.assertEqual(passed["fatal_errors"], [])
        self.assertEqual(passed["tick_count"], 12)
        self.assertIn(
            "strategy-replay-workbench/185: foreground process exited during collection",
            passed["census_churn"][0],
        )

        failed_rows = [_tick(started + i * 5, self.release) for i in range(12)]
        failed_rows[1]["board_error"] = (
            "herdr-projects set board.agents 12 timed out after 4s"
        )
        failed = install_if_behind.evaluate_controller_ticks(
            failed_rows,
            target_release=self.release,
            install_started_at=started,
            min_ticks=12,
        )
        self.assertFalse(failed["passed"])
        self.assertTrue(
            any(str(reason).startswith("board_error:") for reason in failed["reasons"])
        )

        census_rows = [_tick(started + i * 5, self.release) for i in range(12)]
        census_rows[0]["board_agent_census"] = {
            "errors": ["mac-ops/61: ps returned no process rows"],
        }
        census_failed = install_if_behind.evaluate_controller_ticks(
            census_rows,
            target_release=self.release,
            install_started_at=started,
            min_ticks=12,
        )
        self.assertFalse(census_failed["passed"])
        self.assertTrue(
            any(
                "ps returned no process rows" in str(reason)
                for reason in census_failed["reasons"]
            )
        )

        mixed_rows = [_tick(started + i * 5, self.release) for i in range(12)]
        mixed_rows[2]["board_agent_census"] = {
            "errors": [
                "strategy-replay-workbench/185: foreground process exited during collection; ps returned no process rows"
            ],
        }
        mixed = install_if_behind.evaluate_controller_ticks(
            mixed_rows,
            target_release=self.release,
            install_started_at=started,
            min_ticks=12,
        )
        self.assertFalse(mixed["passed"], mixed)
        self.assertEqual(mixed["census_churn"], [])

    def test_observe_waits_past_install_clock_for_tick_quota(self):
        install_started_at = 1_000.0
        clock = {"t": install_started_at + 200.0}
        rows = [_tick(install_started_at + i * 5, self.release) for i in range(10)]
        rows[3]["board_agent_census"] = {
            "errors": [
                "strategy-replay-workbench/185: foreground process exited during collection"
            ],
        }
        _write(self.state, rows)
        sleeps = []

        def fake_time():
            return clock["t"]

        def fake_sleep(seconds):
            sleeps.append(seconds)
            clock["t"] += seconds
            with (self.state / "controller.jsonl").open(
                "a", encoding="utf-8"
            ) as handle:
                handle.write(json.dumps(_tick(clock["t"], self.release)) + "\n")
                handle.write(json.dumps(_tick(clock["t"], self.release)) + "\n")

        install_if_behind.time.time = fake_time
        install_if_behind.time.sleep = fake_sleep
        summary = install_if_behind.observe_controller(
            self.state,
            target_release=self.release,
            install_started_at=install_started_at,
            observe_seconds=180.0,
            poll_interval=5.0,
        )
        self.assertTrue(sleeps)
        self.assertTrue(summary["passed"], summary)
        self.assertGreaterEqual(summary["tick_count"], 12)
        self.assertEqual(summary["reasons"], [])
        self.assertTrue(summary["census_churn"])

    def test_controller_failure_stops_observation_for_rollback(self):
        install_started_at = 5_000.0
        clock = {"t": install_started_at + 1.0}
        row = _tick(install_started_at, self.release)
        row["board_error"] = "herdr-projects set board.agents 12 timed out after 4s"
        _write(self.state, [row])
        sleeps = []
        install_if_behind.time.time = lambda: clock["t"]
        install_if_behind.time.sleep = lambda seconds: sleeps.append(seconds)
        summary = install_if_behind.observe_controller(
            self.state,
            target_release=self.release,
            install_started_at=install_started_at,
            observe_seconds=180.0,
            poll_interval=5.0,
        )
        self.assertEqual(sleeps, [])
        self.assertFalse(summary["passed"])
        self.assertTrue(
            any(str(reason).startswith("board_error:") for reason in summary["reasons"])
        )
        self.assertFalse(
            any(
                str(reason).startswith("insufficient_controller_ticks")
                for reason in summary["reasons"]
            )
        )

    def test_zero_slots_still_fail_immediately(self):
        install_started_at = 8_000.0
        clock = {"t": install_started_at + 1.0}
        row = _tick(install_started_at, self.release)
        row["board"]["decision"]["target"] = 0
        _write(self.state, [row])
        sleeps = []
        install_if_behind.time.time = lambda: clock["t"]
        install_if_behind.time.sleep = lambda seconds: sleeps.append(seconds)
        summary = install_if_behind.observe_controller(
            self.state,
            target_release=self.release,
            install_started_at=install_started_at,
            observe_seconds=180.0,
            poll_interval=5.0,
        )
        self.assertEqual(sleeps, [])
        self.assertFalse(summary["passed"])
        self.assertIn("board_slots_dropped_to_zero_without_veto", summary["reasons"])

    def test_zero_slot_board_before_install_keeps_the_install(self):
        started = 9_000.0

        # The board was already parked at zero slots before the install: the
        # admission limit was 0 before the tick, so nothing dropped.
        parked_rows = [_tick(started + i * 5, self.release) for i in range(12)]
        for row in parked_rows:
            row["board"]["current"] = 0
            row["board"]["decision"]["target"] = 0
            row["board"]["decision"]["active"] = 0
        parked = install_if_behind.evaluate_controller_ticks(
            parked_rows,
            target_release=self.release,
            install_started_at=started,
            min_ticks=12,
        )
        self.assertEqual(parked["unexplained_zero_board_slots"], [])
        self.assertTrue(parked["passed"], parked)
        self.assertNotIn(
            "board_slots_dropped_to_zero_without_veto", parked["reasons"]
        )

        clock = {"t": started + 1.0}
        _write(self.state, [parked_rows[0]])
        sleeps = []
        install_if_behind.time.time = lambda: clock["t"]
        install_if_behind.time.sleep = lambda seconds: sleeps.append(seconds)
        summary = install_if_behind.observe_controller(
            self.state,
            target_release=self.release,
            install_started_at=started,
            observe_seconds=0.0,
        )
        self.assertEqual(sleeps, [])
        self.assertTrue(summary["passed"], summary)
        self.assertNotIn(
            "board_slots_dropped_to_zero_without_veto", summary["reasons"]
        )

        # A drop to zero caused by the install still rolls the install back.
        dropped_rows = [_tick(started + i * 5, self.release) for i in range(12)]
        for row in dropped_rows:
            row["board"]["decision"]["target"] = 0
        dropped = install_if_behind.evaluate_controller_ticks(
            dropped_rows,
            target_release=self.release,
            install_started_at=started,
            min_ticks=12,
        )
        self.assertTrue(dropped["unexplained_zero_board_slots"])
        self.assertFalse(dropped["passed"])
        self.assertIn(
            "board_slots_dropped_to_zero_without_veto", dropped["reasons"]
        )


if __name__ == "__main__":
    unittest.main()
