"""The tick's external calls are bounded.

The tick that reads the board has 600 seconds. A call that hangs must not
use them: the helper that runs the calls gives every call a bound, names
the call it skipped, and lets the rest of the tick finish.

`overnight` and `coord-tick` are scripts without a .py suffix, so they are
loaded by path.
"""
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
OVERNIGHT = ROOT / "coordinator" / "overnight" / "overnight"
COORD_TICK = ROOT / "coordinator" / "pi" / "bin" / "coord-tick"

overnight = None
coord_tick = None


def load(path, name):
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def load_overnight():
    global overnight
    if overnight is None:
        overnight = load(OVERNIGHT, "overnight_bounds")
    return overnight


def load_coord_tick():
    global coord_tick
    if coord_tick is None:
        coord_tick = load(COORD_TICK, "coord_tick_bounds")
    return coord_tick


class CallBoundTests(unittest.TestCase):
    """The helper that runs the external calls."""

    def setUp(self):
        self.overnight = load_overnight()

    def test_a_hanging_call_is_skipped_and_named(self):
        stderr = io.StringIO()
        started = time.monotonic()
        with redirect_stderr(stderr):
            out = self.overnight.run(
                ["/bin/sh", "-c", "sleep 30"], 1, time.monotonic() + 60, optional=True
            )
        elapsed = time.monotonic() - started
        self.assertIsNone(out)
        self.assertLess(elapsed, 15, "the call was not bounded")
        self.assertIn("skipped", stderr.getvalue())
        self.assertIn("timed out", stderr.getvalue())

    def test_a_call_that_ignores_the_first_signal_still_ends(self):
        stderr = io.StringIO()
        started = time.monotonic()
        with redirect_stderr(stderr):
            out = self.overnight.run(
                ["/bin/sh", "-c", "trap '' TERM; sleep 30"],
                1,
                time.monotonic() + 60,
                optional=True,
            )
        elapsed = time.monotonic() - started
        self.assertIsNone(out)
        self.assertLess(elapsed, 15, "the call held the tick past its bound")

    def test_a_call_that_fails_is_a_refusal_and_not_a_skip(self):
        with self.assertRaises(self.overnight.RepoError):
            self.overnight.run(
                ["/bin/sh", "-c", "echo boom >&2; exit 3"],
                5,
                time.monotonic() + 60,
                optional=True,
            )

    def test_a_call_that_is_not_optional_still_ends_the_read(self):
        with self.assertRaises(SystemExit):
            self.overnight.run(["/bin/sh", "-c", "sleep 30"], 1, time.monotonic() + 60)


class BoardReadBoundTests(unittest.TestCase):
    """The board read reads its repositories at the same time."""

    def setUp(self):
        self.overnight = load_overnight()

    def test_one_stalled_repository_costs_one_timeout_and_not_one_per_repository(self):
        script = (
            "import sys\n"
            "sys.path.insert(0, %r)\n"
            "import time\n"
            "time.sleep(30)\n"
        ) % str(ROOT)
        started = time.monotonic()
        with tempfile.TemporaryDirectory() as scratch:
            gh = Path(scratch) / "gh"
            gh.write_text("#!/bin/sh\nsleep 30\n")
            gh.chmod(0o755)
            env = {"PATH": f"{scratch}:{os.environ.get('PATH', '')}"}
            issues = [
                {"repo": "a/b", "number": 1},
                {"repo": "c/d", "number": 2},
                {"repo": "e/f", "number": 3},
            ]
            with patch.dict(os.environ, env):
                with patch.object(self.overnight, "GH_TIMEOUT", 1):
                    stderr = io.StringIO()
                    with redirect_stderr(stderr):
                        bodies, unread, _numbers = self.overnight.read_bodies(
                            issues, time.monotonic() + 60
                        )
        elapsed = time.monotonic() - started
        self.assertEqual(bodies, {})
        self.assertEqual(sorted(unread), ["a/b", "c/d", "e/f"])
        self.assertLess(elapsed, 20, "the repositories were read one after another")
        self.assertIn("skipped", stderr.getvalue())


class ModelCheckBoundTests(unittest.TestCase):
    """The tick's model check is bounded and names the skip."""

    def setUp(self):
        self.tick = load_coord_tick()

    def test_a_hanging_model_check_is_skipped_and_named(self):
        # The process is made before the patch, so the patch cannot reach
        # the call that makes it.
        process = subprocess.Popen(
            ["/bin/sh", "-c", "trap '' TERM; sleep 30"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        with tempfile.TemporaryDirectory() as scratch:
            log = Path(scratch) / "tick.log"
            with patch.object(self.tick, "LOG_PATH", log):
                with patch.object(self.tick, "MODEL_CHECK_TIMEOUT", 1):
                    with patch.object(self.tick.subprocess, "Popen", return_value=process):
                        started = time.monotonic()
                        answer = self.tick.model_available({})
                        elapsed = time.monotonic() - started
                    written = log.read_text() if log.exists() else ""
        self.assertTrue(answer, "a check that cannot answer says yes")
        self.assertLess(elapsed, 15, "the model check was not bounded")
        self.assertIn("skipped", written)


if __name__ == "__main__":
    unittest.main()
