"""The lane's decisions board path comes from the environment.

The lane raises one item on the decisions board when a pull request uses
its review rounds. A test must never write the board Shyam reads, so the
path comes from the environment and a test points it at a scratch file.
These tests prove both: the environment sets the path, and the board
Shyam reads is never named as the destination when the lane raises an item.
"""

import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
LANE_DIR = ROOT / "coordinator" / "overnight"
BIN_DIR = ROOT / "coordinator" / "bin"
REAL_BOARD = Path("/Users/shyamsivakumar/Code/coordinator/decisions.json")

for _folder in (LANE_DIR, BIN_DIR):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

import coordinator.overnight.lane_driver as lane


def load_lane(name):
    """Load the lane driver again, under a name of its own.

    The board path is read when the module loads, so a module loaded with
    the environment set sees the path the environment names.
    """
    loader = importlib.machinery.SourceFileLoader(name, str(LANE_DIR / "lane_driver.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class DecisionsBoardTests(unittest.TestCase):
    def test_the_board_path_comes_from_the_environment(self):
        with tempfile.TemporaryDirectory() as scratch:
            board = Path(scratch) / "decisions.json"
            with patch.dict(os.environ, {"COORDINATOR_DECISIONS": str(board)}):
                importlib.reload(lane.alarms)
                fresh = load_lane("lane_driver_with_environment")
            importlib.reload(lane.alarms)
            self.assertEqual(fresh.DECISIONS_PATH, str(board))

    def test_the_item_is_written_to_the_scratch_board_and_to_no_other_path(self):
        targets = []
        real_update = lane.alarms.board_update

        def record(target, *args, **kwargs):
            targets.append(str(target))
            return real_update(target, *args, **kwargs)

        with tempfile.TemporaryDirectory() as scratch:
            board = Path(scratch) / "decisions.json"
            board.write_text(json.dumps({"items": []}))
            with patch.object(lane, "DECISIONS_PATH", str(board)), \
                    patch.object(lane.alarms, "board_update", record):
                lane.gate_round_decision("fixture/repo", 20, "a" * 40, {})
            items = json.loads(board.read_text())["items"]
        self.assertEqual(targets, [str(board)])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "lane-gate-rounds-fixture-repo-20")

    def test_the_real_board_holds_no_item_of_this_test(self):
        board = json.loads(REAL_BOARD.read_text()) if REAL_BOARD.exists() else {"items": []}
        ids = [item.get("id") for item in board.get("items", [])]
        self.assertNotIn("lane-gate-rounds-fixture-repo-20", ids)


class LedgerTests(unittest.TestCase):
    def test_a_missing_ledger_starts_empty(self):
        with tempfile.TemporaryDirectory() as scratch:
            with patch.object(lane, "LEDGER", str(Path(scratch) / "lanes-ledger.json")):
                self.assertEqual(lane.load_ledger(), {})

    def test_a_corrupt_ledger_stops_the_pass_and_is_left_as_is(self):
        with tempfile.TemporaryDirectory() as scratch:
            ledger = Path(scratch) / "lanes-ledger.json"
            ledger.write_bytes(b'{"a": 1, "trunc')
            with patch.object(lane, "LEDGER", str(ledger)), \
                    patch.object(lane, "run_pass") as run_pass, \
                    patch.object(lane, "api_remaining") as api_remaining:
                with self.assertRaises(SystemExit) as stop:
                    lane.main()
            run_pass.assert_not_called()
            api_remaining.assert_not_called()
            self.assertEqual(ledger.read_bytes(), b'{"a": 1, "trunc')
            self.assertEqual(list(Path(scratch).iterdir()), [ledger])
        self.assertIn("lane: REFUSED: the ledger", str(stop.exception.code))

    def test_a_failed_save_keeps_the_old_ledger_and_leaves_no_temporary(self):
        with tempfile.TemporaryDirectory() as scratch:
            ledger = Path(scratch) / "lanes-ledger.json"
            ledger.write_text('{"old": 1}')
            with patch.object(lane, "LEDGER", str(ledger)), \
                    patch.object(lane.os, "replace", side_effect=OSError("disk")):
                with self.assertRaises(OSError):
                    lane.save_ledger({"new": 2})
            self.assertEqual(json.loads(ledger.read_text()), {"old": 1})
            self.assertEqual(list(Path(scratch).iterdir()), [ledger])

    def test_a_failed_board_write_leaves_no_temporary(self):
        with tempfile.TemporaryDirectory() as scratch:
            board = Path(scratch) / "decisions.json"
            with patch.object(lane.alarms.os, "replace", side_effect=OSError("disk")):
                self.assertFalse(lane.alarms.write_board(board, {"items": []}))
            self.assertEqual(list(Path(scratch).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
