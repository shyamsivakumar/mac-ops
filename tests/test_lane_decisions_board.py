"""The lane's decisions board path and its round-cap stop.

A pull request at the review-round cap goes on the coordinator's stuck
list, not on the decisions board Shyam reads. A test must never write
that board, so its path comes from the environment and a test points it
at a scratch file. These tests prove the environment sets the path, the
cap adds one stuck entry and no decisions item (also when the lane runs
twice), and gatekeep's skip counts leave the entry alone.
"""

import argparse
import importlib.machinery
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
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
from tests.test_gatekeep_backstop_reviewer import load_coordq


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
                fresh = load_lane("lane_driver_with_environment")
            self.assertEqual(fresh.DECISIONS_PATH, str(board))

    def test_the_cap_adds_one_stuck_entry_and_no_decisions_item(self):
        coordq = load_coordq()
        calls = []

        def run(cmd, timeout=150):
            calls.append(cmd)
            coordq.cmd_stuck(argparse.Namespace(ref=cmd[2], head=cmd[4] if "--head" in cmd else "", clear="--clear" in cmd))
            return ""

        with tempfile.TemporaryDirectory() as scratch:
            board = Path(scratch) / "decisions.json"
            board.write_text(json.dumps({"items": [{"id": "other"}]}))
            coordq.DIR = scratch
            coordq.save({"next": 1, "items": []})
            with patch.object(lane, "DECISIONS_PATH", str(board)), \
                    patch.object(lane, "DRY", False), patch.object(lane, "run", run), \
                    redirect_stdout(io.StringIO()):
                lane.gate_round_stuck("fixture/repo", 20, "a" * 40, {})
                lane.gate_round_stuck("fixture/repo", 20, "a" * 40, {})
            entries = coordq.load()["roundsStuck"]
            items = json.loads(board.read_text())["items"]
        self.assertEqual(entries, {"fixture/repo#20": {"head": "a" * 40}})
        self.assertEqual(items, [{"id": "other"}])
        self.assertEqual(len(calls), 2)

    def test_gatekeep_counts_leave_the_rounds_entry_alone(self):
        coordq = load_coordq()
        with tempfile.TemporaryDirectory() as scratch:
            coordq.DIR = scratch
            coordq.save({"next": 1, "items": [], "roundsStuck": {"fixture/repo#20": {"head": "a"}}})
            coordq.write_counts({}, set(), [], False)
            kept = coordq.load()["roundsStuck"]
        self.assertEqual(list(kept), ["fixture/repo#20"])

    def test_the_real_board_holds_no_item_of_this_test(self):
        board = json.loads(REAL_BOARD.read_text()) if REAL_BOARD.exists() else {"items": []}
        ids = [item.get("id") for item in board.get("items", [])]
        self.assertNotIn("lane-gate-rounds-fixture-repo-20", ids)


if __name__ == "__main__":
    unittest.main()
