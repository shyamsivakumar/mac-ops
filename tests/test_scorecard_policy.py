"""Scorecard passes review_policy into shadow replay."""

from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reviewer_audit import __main__ as cli
from reviewer_audit import board_io
from reviewer_audit.metrics import ShadowVerdict


class TestScorecardReviewPolicy(unittest.TestCase):
    def test_legacy_policy_reaches_replay(self):
        manifest = Path(__file__).resolve().parents[1] / "reviewer_audit/manifest.json"
        captured: list[str] = []

        def fake_replay(bundle, **kwargs):
            captured.append(kwargs.get("review_policy", ""))
            return [ShadowVerdict(True, [], [], "saved", 1, error=False)]

        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(board_io, "DEFAULT_BOARD_TASKS", Path(tmpdir)),
            patch.object(cli, "compute_loop_stats") as loops,
            patch.object(cli, "write_scorecard"),
            patch.object(cli, "summarize_retrospective_flips", return_value={}),
            patch("reviewer_audit.shadow.replay_bundle", side_effect=fake_replay),
        ):
            task_path = Path(tmpdir) / "llmwiki" / "10" / "task.json"
            task_path.parent.mkdir(parents=True)
            task_path.write_text(json.dumps({"reviews": []}))
            loops.return_value.median_rounds = 1.0
            loops.return_value.p90_rounds = 2.0
            args = argparse.Namespace(
                manifest=str(manifest),
                out="/tmp/mo18-policy-test",
                limit=1,
                repeats=1,
                deterministic=True,
                heavy=False,
                judge_samples=False,
                review_policy="legacy",
                baseline_scorecard="",
            )
            self.assertEqual(cli.cmd_scorecard(args), 0)
        self.assertEqual(captured, ["legacy"])


if __name__ == "__main__":
    unittest.main()
