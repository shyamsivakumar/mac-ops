"""The coordinator turn-cap launchd job keeps the same shape as the dispatch job."""

from __future__ import annotations

import plistlib
import tempfile
import unittest
from pathlib import Path

import install_coordinator

CHECKOUT = Path(__file__).resolve().parents[1]


class TestTurncapPlist(unittest.TestCase):
    def setUp(self):
        self.home = Path("/Users/example")
        rendered = install_coordinator.render_plists(CHECKOUT, self.home)
        self.rendered = {target.name: data for data, target in rendered}

    def test_job_is_rendered_with_the_home_token_resolved(self):
        self.assertIn("dev.coordinator.turncap.plist", self.rendered)
        data = self.rendered["dev.coordinator.turncap.plist"]
        self.assertNotIn(b"@HOME@", data)
        parsed = plistlib.loads(data)
        self.assertEqual(parsed["Label"], "dev.coordinator.turncap")

    def test_job_runs_the_turn_cap_monitor_and_stays_alive(self):
        parsed = plistlib.loads(self.rendered["dev.coordinator.turncap.plist"])
        self.assertEqual(
            parsed["ProgramArguments"],
            ["/usr/bin/python3", "/Users/example/Code/coordinator/loop/turn_cap.py"],
        )
        self.assertIs(parsed["RunAtLoad"], True)
        self.assertIs(parsed["KeepAlive"], True)

    def test_job_env_resolves_home_and_unbuffers_stdout(self):
        parsed = plistlib.loads(self.rendered["dev.coordinator.turncap.plist"])
        env = parsed["EnvironmentVariables"]
        self.assertEqual(env["HOME"], "/Users/example")
        self.assertEqual(env["PYTHONUNBUFFERED"], "1")
        self.assertIn("/Users/example/.local/bin", env["PATH"])

    def test_job_logs_to_the_coordinator_log_directory(self):
        parsed = plistlib.loads(self.rendered["dev.coordinator.turncap.plist"])
        self.assertEqual(
            parsed["StandardOutPath"], "/Users/example/Library/Logs/coordinator/turncap.log"
        )
        self.assertEqual(parsed["StandardErrorPath"], parsed["StandardOutPath"])

    def test_log_dirs_cover_every_rendered_job(self):
        rendered = install_coordinator.render_plists(CHECKOUT, self.home)
        dirs = install_coordinator.log_dirs(rendered)
        self.assertIn(Path("/Users/example/Library/Logs/coordinator"), dirs)
        self.assertIn(Path("/Users/example/Code/coordinator/queue"), dirs)

    def test_ensure_log_dirs_creates_missing_directories_once(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "Logs" / "coordinator"
            created = install_coordinator.ensure_log_dirs({missing})
            self.assertEqual(created, [missing])
            self.assertTrue(missing.is_dir())
            self.assertEqual(install_coordinator.ensure_log_dirs({missing}), [])


if __name__ == "__main__":
    unittest.main()
