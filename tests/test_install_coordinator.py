"""The coordinator turn-cap launchd job keeps the same shape as the dispatch job."""

from __future__ import annotations

import fcntl
import importlib.machinery
import importlib.util
import os
import plistlib
import signal
import subprocess
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


class TestPiCoordinatorFiles(unittest.TestCase):
    def setUp(self):
        self.home = Path("/Users/example")
        self.plan = {
            target: (source, mode)
            for source, target, mode in install_coordinator.plan(CHECKOUT, self.home)
        }

    def test_guard_profile_and_settings_map_to_the_live_coordinator_paths(self):
        for relative in (
            "extensions/coordinator.ts",
            "coordinator.sb",
            "settings.json",
            "phone-relay/CLAUDE.md",
        ):
            source, mode = self.plan[self.home / ".pi/agent-coordinator" / relative]
            self.assertEqual(source, CHECKOUT / "coordinator/pi" / relative)
            self.assertEqual(mode, 0o644)

    def test_launchers_map_to_the_local_bin_directory(self):
        for name in ("coord-pi", "coord-ask", "coord-phone"):
            source, mode = self.plan[self.home / ".local/bin" / name]
            self.assertEqual(source, CHECKOUT / "coordinator/pi/bin" / name)
            self.assertEqual(mode, 0o755)

    def test_install_writes_the_pi_files_with_their_modes(self):
        with temp_home() as td:
            home = Path(td)
            with redirect_stdout(StringIO()):
                install_coordinator.install(CHECKOUT, False, home)
            guard = home / ".pi/agent-coordinator/extensions/coordinator.ts"
            self.assertEqual(
                guard.read_bytes(),
                (CHECKOUT / "coordinator/pi/extensions/coordinator.ts").read_bytes(),
            )
            self.assertEqual(guard.stat().st_mode & 0o777, 0o644)
            launcher = home / ".local/bin/coord-pi"
            self.assertEqual(
                launcher.read_bytes(), (CHECKOUT / "coordinator/pi/bin/coord-pi").read_bytes()
            )
            self.assertEqual(launcher.stat().st_mode & 0o777, 0o755)

    def test_install_is_idempotent_for_the_pi_files(self):
        with temp_home() as td:
            home = Path(td)
            with redirect_stdout(StringIO()):
                install_coordinator.install(CHECKOUT, False, home)
                install_coordinator.install(CHECKOUT, False, home)
            self.assertEqual(
                install_coordinator.changes(CHECKOUT, home),
                [],
            )


class TestTickJob(unittest.TestCase):
    """The tick job runs the headless tick every five minutes."""

    def setUp(self):
        self.home = Path("/Users/example")
        rendered = install_coordinator.render_plists(CHECKOUT, self.home)
        self.rendered = {target.name: data for data, target in rendered}

    def test_job_is_rendered_with_the_home_token_resolved(self):
        self.assertIn("dev.coordinator.tick.plist", self.rendered)
        data = self.rendered["dev.coordinator.tick.plist"]
        self.assertNotIn(b"@HOME@", data)
        parsed = plistlib.loads(data)
        self.assertEqual(parsed["Label"], "dev.coordinator.tick")

    def test_job_runs_the_tick_launcher_every_five_minutes(self):
        parsed = plistlib.loads(self.rendered["dev.coordinator.tick.plist"])
        self.assertEqual(
            parsed["ProgramArguments"], ["/Users/example/.local/bin/coord-tick"]
        )
        self.assertEqual(parsed["StartInterval"], 300)

    def test_job_does_not_run_a_tick_at_load(self):
        parsed = plistlib.loads(self.rendered["dev.coordinator.tick.plist"])
        self.assertIsNot(parsed.get("RunAtLoad"), True)

    def test_job_logs_into_the_coordinator_log_directory(self):
        parsed = plistlib.loads(self.rendered["dev.coordinator.tick.plist"])
        self.assertEqual(
            parsed["StandardOutPath"],
            "/Users/example/Library/Logs/coordinator/tick.log",
        )
        self.assertEqual(parsed["StandardErrorPath"], parsed["StandardOutPath"])

    def test_log_dirs_cover_the_tick_job(self):
        rendered = install_coordinator.render_plists(CHECKOUT, self.home)
        dirs = install_coordinator.log_dirs(rendered)
        self.assertIn(Path("/Users/example/Library/Logs/coordinator"), dirs)


class TestTickLauncher(unittest.TestCase):
    """The tick launcher runs one headless pi and never two at once."""

    def launcher(self):
        path = CHECKOUT / "coordinator/pi/bin/coord-tick"
        loader = importlib.machinery.SourceFileLoader("coord_tick", str(path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module

    def test_launcher_maps_to_the_local_bin_directory(self):
        home = Path("/Users/example")
        plan = {
            target: (source, mode)
            for source, target, mode in install_coordinator.plan(CHECKOUT, home)
        }
        source, mode = plan[home / ".local/bin/coord-tick"]
        self.assertEqual(source, CHECKOUT / "coordinator/pi/bin/coord-tick")
        self.assertEqual(mode, 0o755)

    def test_coord_pi_exports_coord_wake_zero(self):
        launcher = (CHECKOUT / "coordinator/pi/bin/coord-pi").read_text()
        self.assertIn("export COORD_WAKE=0", launcher)

    def test_only_alert_lines_are_alerts(self):
        module = self.launcher()
        self.assertEqual(
            module.alert_lines("NOOP"),
            [],
        )
        self.assertEqual(
            module.alert_lines("done\nALERT: one thing\nnoise\nALERT: two things"),
            ["ALERT: one thing", "ALERT: two things"],
        )

    def test_an_alert_with_a_list_marker_or_emphasis_is_an_alert(self):
        module = self.launcher()
        self.assertEqual(
            module.alert_lines("- ALERT: one thing"),
            ["- ALERT: one thing"],
        )
        self.assertEqual(
            module.alert_lines("**ALERT:** one thing"),
            ["**ALERT:** one thing"],
        )

    def test_prompt_override_replaces_the_default_prompt(self):
        module = self.launcher()
        previous = os.environ.get("COORD_TICK_PROMPT_OVERRIDE")
        os.environ["COORD_TICK_PROMPT_OVERRIDE"] = "Reply exactly NOOP."
        try:
            self.assertEqual(module.prompt(), "Reply exactly NOOP.")
        finally:
            if previous is None:
                del os.environ["COORD_TICK_PROMPT_OVERRIDE"]
            else:
                os.environ["COORD_TICK_PROMPT_OVERRIDE"] = previous
        self.assertIn("loop/tick.md", module.DEFAULT_PROMPT)

    def test_a_second_run_exits_at_the_lock(self):
        with tempfile.TemporaryDirectory(prefix="coord-tick-test-") as tmp:
            lock_path = Path(tmp) / "coord-tick.lock"
            log_path = Path(tmp) / "tick.log"
            held = open(lock_path, "a+")
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                env = dict(os.environ)
                env["COORD_TICK_LOCK"] = str(lock_path)
                env["COORD_TICK_LOG"] = str(log_path)
                result = subprocess.run(
                    [sys.executable, str(CHECKOUT / "coordinator/pi/bin/coord-tick")],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    env=env,
                )
            finally:
                fcntl.flock(held, fcntl.LOCK_UN)
                held.close()
            self.assertEqual(result.returncode, 0)
            self.assertIn("skipped: another tick holds the lock", log_path.read_text())

    def test_the_lock_path_is_the_same_for_every_caller(self):
        module = self.launcher()
        previous = os.environ.pop("COORD_TICK_LOCK", None)
        try:
            first = module.lock_path()
            os.environ["TMPDIR"] = "/tmp/other"
            self.assertEqual(module.lock_path(), first)
        finally:
            if previous is None:
                os.environ.pop("COORD_TICK_LOCK", None)
            else:
                os.environ["COORD_TICK_LOCK"] = previous

    def test_the_process_group_is_killed_by_the_child_pid(self):
        module = self.launcher()
        process = subprocess.Popen(
            ["/bin/sleep", "300"], start_new_session=True
        )
        try:
            module.kill_group(process, signal.SIGTERM)
            self.assertIsNotNone(process.wait(timeout=10))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)

    def test_a_stopped_launcher_kills_the_run_it_started(self):
        module = self.launcher()
        process = subprocess.Popen(
            ["/bin/sleep", "300"], start_new_session=True
        )
        module.RUNNING.append(process)
        try:
            with self.assertRaises(SystemExit):
                module.stop_on_signal(signal.SIGTERM, None)
            self.assertIsNotNone(process.wait(timeout=10))
        finally:
            module.RUNNING.clear()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)


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
