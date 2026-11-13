"""The coordinator turn-cap launchd job keeps the same shape as the dispatch job."""

from __future__ import annotations

import plistlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install_coordinator

CHECKOUT = ROOT


def temp_home():
    """A home directory the installer can write. The installer pins every
    directory below the home path without following symlinks, and the system
    temporary directory sits under a symlinked /var, so the home path is used."""
    return tempfile.TemporaryDirectory(dir=Path.home(), prefix="mac-ops-test-")


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

    def test_log_dirs_cover_the_turn_cap_job(self):
        rendered = install_coordinator.render_plists(CHECKOUT, self.home)
        dirs = install_coordinator.log_dirs(rendered)
        self.assertIn(Path("/Users/example/Library/Logs/coordinator"), dirs)

    def test_home_token_is_escaped_for_xml(self):
        home = Path("/Users/a&b")
        rendered = install_coordinator.render_plists(CHECKOUT, home)
        data = dict((target.name, data) for data, target in rendered)[
            "dev.coordinator.turncap.plist"
        ]
        parsed = plistlib.loads(data)
        self.assertEqual(
            parsed["ProgramArguments"][1], "/Users/a&b/Code/coordinator/loop/turn_cap.py"
        )

    def test_unreadable_plist_is_reported_not_crashed(self):
        with self.assertRaises(RuntimeError):
            install_coordinator.log_dirs([(b"<plist><dict>", Path("broken.plist"))])

    def test_monitor_pids_parses_only_process_ids(self):
        output = "58640 /usr/bin/python3 /Users/x/Code/coordinator/loop/turn_cap.py\n"
        self.assertEqual(install_coordinator.monitor_pids(output), [58640])

    def test_ensure_log_dirs_creates_missing_directories_once(self):
        with temp_home() as td:
            home = Path(td)
            missing = home / "Library/Logs/coordinator"
            created, refused = install_coordinator.ensure_log_dirs({missing}, home)
            self.assertEqual(created, [missing])
            self.assertEqual(refused, [])
            self.assertTrue(missing.is_dir())
            created, refused = install_coordinator.ensure_log_dirs({missing}, home)
            self.assertEqual(created, [])
            self.assertEqual(refused, [])

    def test_ensure_log_dirs_leaves_other_checkouts_alone(self):
        with temp_home() as td:
            home = Path(td)
            other = home / "Code/coordinator/queue"
            created, refused = install_coordinator.ensure_log_dirs({other}, home)
            self.assertEqual((created, refused), ([], []))
            self.assertFalse(other.exists())

    def test_symlinked_level_is_refused_and_nothing_is_written_through_it(self):
        with temp_home() as td:
            home = Path(td)
            target = home / "outside"
            target.mkdir()
            (home / "Library").symlink_to(target)
            missing = home / "Library/Logs/coordinator"
            with redirect_stdout(StringIO()):
                created, refused = install_coordinator.ensure_log_dirs({missing}, home)
            self.assertEqual(created, [])
            self.assertEqual(refused, [missing])
            self.assertFalse((target / "Logs").exists())

    def test_launchd_pid_is_read_from_either_launchctl_form(self):
        self.assertEqual(
            install_coordinator.parse_launchd_pid('\t"PID" = 58640;\n'), 58640
        )
        self.assertEqual(install_coordinator.parse_launchd_pid("\tpid = 58640\n"), 58640)
        self.assertIsNone(install_coordinator.parse_launchd_pid("\tno pid here\n"))

    def test_manual_monitors_excludes_the_launchd_owned_process(self):
        self.assertEqual(install_coordinator.manual_pids([58640], 58640), [])
        self.assertEqual(install_coordinator.manual_pids([58640, 999], 58640), [999])
        self.assertEqual(install_coordinator.manual_pids([58640], None), [58640])

    def test_monitor_pattern_needs_a_python_interpreter_and_the_script_path(self):
        pattern = install_coordinator.MONITOR_PATTERN
        self.assertRegex(
            "/usr/bin/python3 /Users/x/Code/coordinator/loop/turn_cap.py", pattern
        )
        self.assertRegex(
            "/usr/bin/python3 /Users/x/Code/coordinator/loop/turn_cap.py --dry-run",
            pattern,
        )
        self.assertNotRegex("/bin/grep turn_cap.py", pattern)
        self.assertNotRegex("/bin/cat /Users/x/loop/turn_cap.py", pattern)
        self.assertNotRegex(
            "/usr/bin/python3 /tmp/mo_gate.py MO-192 runs loop/turn_cap.py with KeepAlive",
            pattern,
        )


class TestInstallPath(unittest.TestCase):
    def test_install_creates_the_log_directory_and_writes_the_job(self):
        with temp_home() as td:
            home = Path(td)
            with redirect_stdout(StringIO()):
                install_coordinator.install(CHECKOUT, False, home)
            self.assertTrue((home / "Library/Logs/coordinator").is_dir())
            written = (home / "Library/LaunchAgents/dev.coordinator.turncap.plist").read_bytes()
            expected = dict(
                (target.name, data)
                for data, target in install_coordinator.render_plists(CHECKOUT, home)
            )
            self.assertEqual(written, expected["dev.coordinator.turncap.plist"])
            self.assertFalse((home / "Code/coordinator/queue").exists())

    def test_install_is_idempotent_for_the_log_directory(self):
        with temp_home() as td:
            home = Path(td)
            with redirect_stdout(StringIO()):
                install_coordinator.install(CHECKOUT, False, home)
                install_coordinator.install(CHECKOUT, False, home)
            self.assertTrue((home / "Library/Logs/coordinator").is_dir())


if __name__ == "__main__":
    unittest.main()
