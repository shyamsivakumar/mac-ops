import contextlib
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bot1_rollback_dry_run as dry_run

CURRENT = "c6b38eb588d7d3e129f8a581e8aaeb7219be0faf"
PREVIOUS = "402cac667cfdafa41b60193b24e17a5cac94bfb5"


def deployment(deployment_id, status, sha):
    return {"id": deployment_id, "status": status, "meta": {"commitHash": sha}}


def run_main(deployments):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = dry_run.main(lambda: deployments)
    return code, out.getvalue(), err.getvalue()


class Bot1RollbackDryRunTests(unittest.TestCase):
    def test_rollback_is_newest_earlier_deployment_with_a_different_commit(self):
        code, out, _ = run_main(
            [
                deployment("d4", "SUCCESS", CURRENT),
                deployment("d3", "REMOVED", PREVIOUS),
                deployment("d2", "REMOVED", CURRENT),
                deployment("d1", "REMOVED", "c5d2eabf" + "0" * 32),
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn(f"recorded rollback SHA: {PREVIOUS}", out)
        self.assertIn(f"production deployment: d4 at {CURRENT}", out)
        self.assertIn(f"--break-glass-rollback {PREVIOUS}", out)

    def test_missing_rollback_record_exits_non_zero_with_one_line(self):
        code, out, err = run_main(
            [deployment("d2", "SUCCESS", CURRENT), deployment("d1", "REMOVED", CURRENT)]
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(len(err.strip().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
