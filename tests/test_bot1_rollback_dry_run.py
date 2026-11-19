import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import bot1_rollback_dry_run as dry_run

CURRENT = "c6b38eb588d7d3e129f8a581e8aaeb7219be0faf"
PREVIOUS = "402cac667cfdafa41b60193b24e17a5cac94bfb5"


def deployment(day, status, sha, meta=None):
    record = {
        "id": f"d{day}",
        "createdAt": f"2026-11-0{day}T00:00:00Z",
        "meta": {"commitHash": sha} if meta is None else meta,
    }
    if status is not ...:
        record["status"] = status
    return record


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
                deployment(3, "SLEEPING", PREVIOUS),
                deployment(5, "QUEUED", "f" * 40),
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn(f"production deployment: d4 at {CURRENT}", out)
        self.assertIn(f"--break-glass-rollback {PREVIOUS}", out)

    def test_unusable_history_exits_non_zero_with_one_line(self):
        success = deployment(4, "SUCCESS", CURRENT)
        older = deployment(1, "REMOVED", PREVIOUS)
        for history in (
            [success, deployment(1, "REMOVED", CURRENT)],
            [success, deployment(3, "REMOVED", None, meta={}), older],
            [success, deployment(3, "SLEEPING", None, meta={}), older],
            [success, deployment(3, ..., CURRENT), older],
            [success, deployment(3, None, CURRENT), older],
            [success, deployment(3, "BOGUS", CURRENT), older],
            [success, deployment(3, [], CURRENT), older],
            [success, deployment(3, {}, CURRENT), older],
            [success, deployment(3, 1, CURRENT), older],
            [success, deployment(1, "REMOVED", PREVIOUS, meta="unavailable")],
            [success, None],
        ):
            code, out, err = run_main(history)
            self.assertEqual((code, out, len(err.splitlines())), (1, "", 1))


if __name__ == "__main__":
    unittest.main()
