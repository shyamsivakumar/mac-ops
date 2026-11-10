#!/usr/bin/env python3
"""Real hub subprocesses and sockets, isolated under a disposable HOME."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
HUB = ROOT / "empryo/bin/emp-hub"


class SingleInstanceProof(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hg-", dir="/tmp")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.directory = self.home / ".empryo-hub"
        self.directory.mkdir()
        shutil.copy(ROOT / "empryo/hub/routing.json", self.directory / "routing.json")
        self.env = {**os.environ, "HOME": str(self.home), "PYTHONDONTWRITEBYTECODE": "1"}
        self.socket = self.directory / "hub.sock"
        self.children = []
        self.addCleanup(self.stop)

    def stop(self):
        for proc in self.children:
            if proc.poll() is None:
                proc.terminate()
            proc.communicate(timeout=5)

    def start(self, *args):
        proc = subprocess.Popen([sys.executable, str(HUB), *args], env=self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.children.append(proc)
        return proc

    def status(self):
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(2)
            client.connect(str(self.socket))
            client.sendall(b'{"method":"call","tool":"emp_hub_status","arguments":{}}\n')
            with client.makefile() as stream:
                reply = json.loads(stream.readline())
        self.assertTrue(reply["ok"], reply)
        return reply["result"]

    def first_instance(self):
        proc = self.start()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                self.fail(f"first hub exited: {proc.communicate()}")
            try:
                if self.status()["pid"] == proc.pid:
                    return proc
            except (OSError, ValueError):
                pass
            time.sleep(0.01)
        self.fail("first hub did not serve")

    def snapshot(self):
        return {str(p.relative_to(self.directory)): (p.stat().st_ino, p.stat().st_mtime_ns,
                p.read_bytes() if p.is_file() else None)
                for p in self.directory.rglob("*")}

    def test_second_start_changes_nothing(self):
        first = self.first_instance()
        before = self.snapshot()
        second = self.start()
        try:
            out, err = second.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            self.fail("second hub kept running instead of rejecting the lock")
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("already running", out + err)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.status()["pid"], first.pid)

    def test_lock_precedes_reading_stores(self):
        first = self.first_instance()
        (self.directory / "threads.json").write_text("not JSON")
        before = self.snapshot()
        second = self.start()
        out, err = second.communicate(timeout=3)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("already running", out + err)
        self.assertNotIn("JSONDecodeError", out + err)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.status()["pid"], first.pid)

    def test_help_does_not_create_hub_directory(self):
        fresh_home = self.home / "fresh"
        self.env["HOME"] = str(fresh_home)
        proc = self.start("--help")
        out, err = proc.communicate(timeout=3)
        self.assertEqual(proc.returncode, 0, out + err)
        self.assertIn("Usage:", out)
        self.assertFalse(fresh_home.exists())

    def test_arguments_do_not_touch_state(self):
        # Invalid stores ensure argument handling precedes even reading state.
        (self.directory / "threads.json").write_text("not JSON")
        for args in (("--help",), ("--unknown",), ("start", "extra")):
            with self.subTest(args=args):
                before = self.snapshot()
                proc = self.start(*args)
                out, err = proc.communicate(timeout=3)
                self.assertEqual(proc.returncode, 0, out + err)
                self.assertIn("Usage:", out)
                self.assertEqual(self.snapshot(), before)
                self.assertFalse(self.socket.exists())

    def test_help_preserves_live_socket_and_lock_releases_on_exit(self):
        first = self.first_instance()
        before = self.snapshot()
        proc = self.start("--help")
        out, err = proc.communicate(timeout=3)
        self.assertEqual(proc.returncode, 0, out + err)
        self.assertIn("Usage:", out)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.status()["pid"], first.pid)
        first.terminate()
        first.communicate(timeout=5)
        replacement = self.first_instance()
        self.assertEqual(self.status()["pid"], replacement.pid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
