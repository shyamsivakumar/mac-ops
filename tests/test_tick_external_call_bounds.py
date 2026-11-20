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
import shutil
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

    def test_a_descendant_that_ignores_the_signal_does_not_outlive_the_call(self):
        """A descendant that ignores SIGTERM and closes its output dies too.

        The leader is killed first, so the wait ends while the descendant
        is still running. The group is emptied after the leader is gone,
        or the descendant keeps running behind the tick."""
        with tempfile.TemporaryDirectory() as scratch:
            marker = Path(scratch) / "descendant.pid"
            script = (
                "(trap '' TERM; while true; do sleep 1; done) >/dev/null 2>&1 & "
                f"echo $! > {marker}; wait"
            )
            with redirect_stderr(io.StringIO()):
                out = self.overnight.run(
                    ["/bin/sh", "-c", script], 1, time.monotonic() + 60, optional=True
                )
            self.assertIsNone(out)
            pid = int(marker.read_text().strip())
            time.sleep(1)
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

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


class SkipLogTests(unittest.TestCase):
    """A skipped call is written down where it cannot be lost."""

    def setUp(self):
        self.overnight = load_overnight()

    def test_the_skip_is_written_to_the_skip_log(self):
        with tempfile.TemporaryDirectory() as scratch:
            log = Path(scratch) / "skips.log"
            with patch.object(self.overnight, "SKIP_LOG", log):
                with redirect_stderr(io.StringIO()):
                    self.overnight.run(
                        ["/bin/sh", "-c", "sleep 30"],
                        1,
                        time.monotonic() + 60,
                        optional=True,
                    )
            written = log.read_text()
        self.assertIn("skipped", written)
        self.assertIn("sleep 30", written)


class IsolationTests(unittest.TestCase):
    """A test run reaches a fake `gh` and temp logs, not the live ones.

    The environment is set once, when the suite is launched, so every test
    in the run inherits it. These cases check that it is in force: the fake
    `gh` is first on PATH, it fails a call it was not asked to answer, and
    the skip log and the gh usage log are temp files.
    """

    def setUp(self):
        self.overnight = load_overnight()

    def test_the_fake_gh_is_first_on_path(self):
        found = shutil.which("gh")
        self.assertIsNotNone(found, "no gh on PATH")
        self.assertIn("fake gh", Path(found).read_text())

    def test_a_call_the_tests_do_not_ask_for_fails(self):
        result = subprocess.run(["gh", "pr", "view", "1"],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no answer for", result.stderr)

    def test_the_skip_log_is_a_temp_file(self):
        live = Path.home() / "Library/Logs/coordinator/skips.log"
        self.assertNotEqual(self.overnight.SKIP_LOG, live)
        self.assertIn("mac-ops-test-", str(self.overnight.SKIP_LOG))

    def test_the_gh_usage_log_is_a_temp_file(self):
        live = Path.home() / "Library/Logs/coordinator/gh-usage.jsonl"
        self.assertNotEqual(self.overnight.gh_gateway.USAGE_LOG, live)
        self.assertIn("mac-ops-test-", str(self.overnight.gh_gateway.USAGE_LOG))


class CoordqCallBoundTests(unittest.TestCase):
    """The t3mcp call the tick makes with `coordq status` is bounded."""

    def setUp(self):
        self.coordq = load(ROOT / "coordinator" / "bin" / "coordq", "coordq_bounds")

    def test_a_hanging_t3mcp_call_is_named_and_does_not_wait(self):
        scratch = tempfile.mkdtemp()
        script = Path(scratch) / "t3mcp"
        script.write_text("#!/bin/sh\nsleep 30\n")
        script.chmod(0o755)
        with patch.object(self.coordq, "T3MCP", str(script)):
            with patch.object(self.coordq, "T3MCP_TIMEOUT", 1):
                started = time.monotonic()
                code, out = self.coordq.call("t3_thread_list", {})
                elapsed = time.monotonic() - started
        self.assertEqual(code, 1)
        self.assertIn("timed out", out)
        self.assertLess(elapsed, 15, "the t3mcp call was not bounded")


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


class TickRunStopTests(unittest.TestCase):
    """A run the tick kills is a whole group, not one process."""

    def setUp(self):
        self.tick = load_coord_tick()

    def test_a_killed_run_leaves_no_descendant_behind(self):
        with tempfile.TemporaryDirectory() as scratch:
            marker = Path(scratch) / "descendant.pid"
            script = (
                "(trap '' TERM; while true; do sleep 1; done) >/dev/null 2>&1 & "
                f"echo $! > {marker}; wait"
            )
            # The process is made before the patch, so the patch cannot reach
            # the call that makes it.
            process = subprocess.Popen(
                ["/bin/sh", "-c", script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            log = Path(scratch) / "tick.log"
            with patch.object(self.tick, "LOG_PATH", log):
                with patch.object(self.tick, "TIMEOUT_S", 1):
                    with patch.object(self.tick, "RUNNING", []):
                        with patch.object(
                            self.tick.subprocess, "Popen", return_value=process
                        ):
                            code = self.tick.run_tick({}, os.open(os.devnull, 0))
            self.assertEqual(code, 124, "a killed run reports the kill")
            pid = int(marker.read_text().strip())
            time.sleep(1)
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)


if __name__ == "__main__":
    unittest.main()
