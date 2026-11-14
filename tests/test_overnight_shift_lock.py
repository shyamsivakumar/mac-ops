#!/usr/bin/env python3
"""The overnight shift takes its own lock, so two cycles never run at once.

The launchd job fires the shift every five minutes. A cycle takes about a
minute and a half, so the next fire lands long after the cycle ended, but
the lock is what keeps two cycles apart when a person starts a cycle by
hand while the job's cycle runs.
"""
import fcntl
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CHECKOUT = Path(__file__).resolve().parents[1]
OVERNIGHT = CHECKOUT / "coordinator/overnight/overnight"


def load_module():
    """Load the overnight command as a module."""
    loader = importlib.machinery.SourceFileLoader("overnight_shift", str(OVERNIGHT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class TestShiftLock(unittest.TestCase):
    """The shift's lock is one path for every caller."""

    def test_the_lock_path_is_the_same_for_every_caller(self):
        module = load_module()
        previous = os.environ.pop("OVERNIGHT_SHIFT_LOCK", None)
        try:
            first = module.shift_lock_path()
            os.environ["TMPDIR"] = "/tmp/other"
            self.assertEqual(module.shift_lock_path(), first)
            self.assertEqual(first.name, "overnight-shift.lock")
        finally:
            if previous is None:
                os.environ.pop("OVERNIGHT_SHIFT_LOCK", None)
            else:
                os.environ["OVERNIGHT_SHIFT_LOCK"] = previous

    def test_a_free_lock_is_taken(self):
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="overnight-lock-") as tmp:
            lock = Path(tmp) / "overnight-shift.lock"
            os.environ["OVERNIGHT_SHIFT_LOCK"] = str(lock)
            try:
                fd, problem = module.take_shift_lock()
                self.assertIsNotNone(fd)
                self.assertEqual(problem, "")
                module.release_shift_lock(fd)
            finally:
                os.environ.pop("OVERNIGHT_SHIFT_LOCK", None)

    def test_a_held_lock_is_not_taken(self):
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="overnight-lock-") as tmp:
            lock = Path(tmp) / "overnight-shift.lock"
            held = open(lock, "a+")
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.environ["OVERNIGHT_SHIFT_LOCK"] = str(lock)
            try:
                fd, problem = module.take_shift_lock()
                self.assertIsNone(fd)
                self.assertEqual(problem, "")
            finally:
                os.environ.pop("OVERNIGHT_SHIFT_LOCK", None)
                fcntl.flock(held, fcntl.LOCK_UN)
                held.close()

    def test_a_cycle_does_no_work_when_another_one_holds_the_lock(self):
        with tempfile.TemporaryDirectory(prefix="overnight-cycle-") as tmp:
            root = Path(tmp) / "root"
            lock = Path(tmp) / "overnight-shift.lock"
            policy = subprocess.run(
                [sys.executable, str(OVERNIGHT), "policy", "--root", str(root)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(policy.returncode, 0, policy.stderr)
            held = open(lock, "a+")
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            env = dict(os.environ)
            env["OVERNIGHT_SHIFT_LOCK"] = str(lock)
            try:
                result = subprocess.run(
                    [sys.executable, str(OVERNIGHT), "shift", "--root", str(root)],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    env=env,
                )
            finally:
                fcntl.flock(held, fcntl.LOCK_UN)
                held.close()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("another cycle holds the lock", result.stdout)
            self.assertNotIn("shift cycle wrote", result.stdout)


if __name__ == "__main__":
    unittest.main()
