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


def deployment(day, status, sha, meta=None):
    meta = {"commitHash": sha} if meta is None else meta
    return {
        "id": f"d{day}",
        "status": status,
        "createdAt": f"2026-11-0{day}T00:00:00Z",
        "meta": meta,
    }


def run_main(deployments):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = dry_run.main(lambda: deployments)
    return code, out.getvalue(), err.getvalue()


class Bot1RollbackDryRunTests(unittest.TestCase):
    def test_rollback_is_newest_earlier_deployment_with_a_different_commit(self):
        code, out, _ = run_main(
            [
                deployment(1, "REMOVED", "c5d2eabf" + "0" * 32),
                deployment(4, "SUCCESS", CURRENT),
                deployment(2, "REMOVED", CURRENT),
                deployment(3, "REMOVED", PREVIOUS),
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn(f"recorded rollback SHA: {PREVIOUS}", out)
        self.assertIn(f"production deployment: d4 at {CURRENT}", out)
        self.assertIn(f"--break-glass-rollback {PREVIOUS}", out)

    def assert_one_error_line(self, deployments):
        code, out, err = run_main(deployments)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(len(err.strip().splitlines()), 1)

    def test_missing_rollback_record_exits_non_zero_with_one_line(self):
        self.assert_one_error_line(
            [deployment(2, "SUCCESS", CURRENT), deployment(1, "REMOVED", CURRENT)]
        )

    def test_intervening_deployment_without_a_sha_stops_the_run(self):
        self.assert_one_error_line(
            [
                deployment(3, "SUCCESS", CURRENT),
                deployment(2, "REMOVED", None, meta={}),
                deployment(1, "REMOVED", PREVIOUS),
            ]
        )

    def test_malformed_records_exit_with_one_line(self):
        self.assert_one_error_line(
            [
                deployment(2, "SUCCESS", CURRENT),
                deployment(1, "REMOVED", PREVIOUS, meta="unavailable"),
            ]
        )
        self.assert_one_error_line([deployment(2, "SUCCESS", CURRENT), None])


if __name__ == "__main__":
    unittest.main()
