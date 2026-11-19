"""The coordinator turn-cap launchd job keeps the same shape as the dispatch job."""

from __future__ import annotations

import fcntl
import importlib.machinery
import importlib.util
import json
import os
import plistlib
import signal
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install_coordinator

CHECKOUT = ROOT

GIT_ANSWERS = {
    ("rev-parse", "--show-toplevel"): str(CHECKOUT),
    ("rev-parse", "--path-format=absolute", "--git-common-dir"): str(CHECKOUT / ".git"),
    ("symbolic-ref", "--short", "HEAD"): "main",
    ("status", "--porcelain", "--untracked-files=all"): "",
    ("fetch", "origin", "+refs/heads/main:refs/remotes/origin/main"): "",
    ("rev-parse", "HEAD"): "a" * 40,
    ("rev-parse", "refs/remotes/origin/main"): "a" * 40,
}


def fake_git(answers):
    """Answer the installer's git calls from a table instead of a real repo."""
    original = subprocess.check_output

    def check_output(argv, **kwargs):
        if argv[:3] != ["git", "-C", str(CHECKOUT)]:
            return original(argv, **kwargs)
        key = tuple(argv[3:])
        if key in answers:
            return answers[key]
        return original(argv, **kwargs)

    return check_output


@contextmanager
def temp_home():
    """Provide the runtime files required by installed-command smoke checks."""
    with tempfile.TemporaryDirectory(dir=Path.home(), prefix="mac-ops-test-") as td, \
            tempfile.TemporaryDirectory(prefix="mac-ops-runtime-") as runtime:
        runtime_root = Path(runtime)
        queue = runtime_root / "queue"
        queue.mkdir(parents=True)
        (queue / "config.json").write_text('{"cap": 6}')
        t3 = runtime_root / "synthetic-t3mcp"
        t3.write_text("#!/bin/sh\nprintf '%s\\n' '{\"total\": 0}'\n")
        t3.chmod(0o755)
        launchctl = runtime_root / "launchctl"
        launchctl.write_text("#!/bin/sh\nexit 1\n")
        launchctl.chmod(0o755)
        with mock.patch.dict(os.environ, {
            "COORDQ_DIR": str(queue), "COORDQ_T3MCP": str(t3),
            "PATH": str(runtime_root) + os.pathsep + os.environ.get("PATH", ""),
        }):
            with mock.patch.object(subprocess, "check_output", side_effect=fake_git(GIT_ANSWERS)):
                yield td


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
            ["/usr/bin/python3", "/Users/example/.local/bin/turn_cap.py"],
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
            parsed["ProgramArguments"][1], "/Users/a&b/.local/bin/turn_cap.py"
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
            "/usr/bin/python3 /Users/x/.local/bin/turn_cap.py", pattern
        )
        self.assertRegex(
            "/usr/bin/python3 /Users/x/.local/bin/turn_cap.py --dry-run",
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
        for name in ("coord-pi", "coord-ask", "coord-phone", "coord-tick", "kpane", "kshow"):
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
    """The tick job is back (MO-250, mac-ops #267): the plist is in the
    repository, it runs on DeepSeek, and the installer leaves it alone."""

    def setUp(self):
        self.home = Path("/Users/example")
        rendered = install_coordinator.render_plists(CHECKOUT, self.home)
        self.rendered = {target.name: data for data, target in rendered}

    def test_the_tick_plist_is_rendered(self):
        self.assertIn("dev.coordinator.tick.plist", self.rendered)

    def test_the_repository_holds_the_tick_plist(self):
        self.assertTrue(
            (CHECKOUT / "coordinator/launchd/dev.coordinator.tick.plist").exists()
        )

    def test_the_tick_job_is_not_in_the_installers_retired_set(self):
        self.assertNotIn("dev.coordinator.tick", install_coordinator.RETIRED_JOBS)

    def test_the_installer_leaves_an_installed_tick_plist_alone(self):
        with temp_home() as td:
            home = Path(td)
            agents = home / "Library" / "LaunchAgents"
            agents.mkdir(parents=True)
            tick = agents / "dev.coordinator.tick.plist"
            tick.write_text("<plist></plist>")
            notes = install_coordinator.retire_jobs(home)
            self.assertTrue(tick.exists())
            self.assertEqual(notes, [])

    def test_a_home_without_a_tick_plist_is_left_alone(self):
        with temp_home() as td:
            home = Path(td)
            self.assertEqual(install_coordinator.retire_jobs(home), [])

    def test_the_tick_job_runs_the_tick_launcher_every_30_minutes(self):
        parsed = plistlib.loads(self.rendered["dev.coordinator.tick.plist"])
        self.assertEqual(parsed["Label"], "dev.coordinator.tick")
        self.assertEqual(parsed["StartInterval"], 1800)
        self.assertEqual(
            parsed["ProgramArguments"],
            ["/Users/example/.local/bin/coord-tick"],
        )

    def test_the_tick_job_runs_on_deepseek(self):
        parsed = plistlib.loads(self.rendered["dev.coordinator.tick.plist"])
        self.assertEqual(
            parsed["EnvironmentVariables"]["COORD_TICK_MODEL"],
            "deepseek/deepseek-flash",
        )

    def test_the_lanes_job_is_the_only_job_that_runs_the_shift(self):
        parsed = plistlib.loads(self.rendered["dev.coordinator.lanes.plist"])
        self.assertEqual(parsed["StartInterval"], 180)
        self.assertEqual(
            parsed["ProgramArguments"],
            ["/Users/example/.local/bin/overnight", "shift"],
        )
        self.assertNotIn("dev.coordinator.overnight.plist", self.rendered)
        self.assertIn("dev.coordinator.overnight", install_coordinator.RETIRED_JOBS)

    def test_the_installer_removes_an_installed_overnight_plist(self):
        with temp_home() as td:
            home = Path(td)
            agents = home / "Library" / "LaunchAgents"
            agents.mkdir(parents=True)
            old = agents / "dev.coordinator.overnight.plist"
            old.write_text("<plist></plist>")
            install_coordinator.retire_jobs(home)
            self.assertFalse(old.exists())


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

    def test_coord_pi_keeps_wake_on_by_default(self):
        """Refs #346: the launcher defaults wake on and keeps an explicit 0."""
        launcher = (CHECKOUT / "coordinator/pi/bin/coord-pi").read_text()
        self.assertIn('export COORD_WAKE="${COORD_WAKE:-1}"', launcher)
        self.assertNotIn("export COORD_WAKE=0", launcher)

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


class TestLaunchdReload(unittest.TestCase):
    """An install reloads the launchd jobs whose plist it changed.

    launchd reads a plist only when the job is bootstrapped, so a correct
    install that leaves the old job running is not a correct install."""

    def launcher(self, calls):
        """A fake launchctl that records every call and starts nothing."""

        def fake_status(argv, *, capture_error=None):
            calls.append(list(argv))
            if argv[1] == "print":
                # launchd has let the job go.
                return 1
            return 0

        def fake_quiet(argv):
            calls.append(list(argv))
            return None

        return fake_status, fake_quiet

    def test_a_temporary_home_never_starts_launchctl(self):
        with temp_home() as td:
            home = Path(td)
            agents = home / "Library" / "LaunchAgents"
            agents.mkdir(parents=True)
            (agents / "dev.coordinator.turncap.plist").write_bytes(
                plistlib.dumps(
                    {"Label": "dev.coordinator.turncap", "ProgramArguments": ["/bin/true"]}
                )
            )
            calls: list[list[str]] = []
            fake_status, fake_quiet = self.launcher(calls)
            out = StringIO()
            with mock.patch.object(install_coordinator, "run_status", fake_status), \
                    mock.patch.object(install_coordinator, "run_quiet", fake_quiet):
                with redirect_stdout(out):
                    install_coordinator.install(CHECKOUT, False, home)
            self.assertEqual([c for c in calls if c[0] == "launchctl"], [])
            self.assertIn("Skipped the reload of dev.coordinator.turncap", out.getvalue())
            self.assertIn("not the real home", out.getvalue())

    def test_a_changed_job_is_reloaded_with_bootout_then_bootstrap(self):
        with temp_home() as td:
            home = Path(td)
            calls: list[list[str]] = []
            fake_status, fake_quiet = self.launcher(calls)
            # The first install writes every file and touches no job: the
            # home is not the real one.
            with mock.patch.object(install_coordinator, "run_status", fake_status), \
                    mock.patch.object(install_coordinator, "run_quiet", fake_quiet):
                with redirect_stdout(StringIO()):
                    install_coordinator.install(CHECKOUT, False, home)
            self.assertEqual([c for c in calls if c[0] == "launchctl"], [])
            # One installed plist drifts from the checkout. Only that job
            # is a job to reload.
            plist = home / "Library/LaunchAgents/dev.coordinator.turncap.plist"
            parsed = plistlib.loads(plist.read_bytes())
            parsed["EnvironmentVariables"] = dict(
                parsed.get("EnvironmentVariables", {}), MAC_OPS_PROOF="1"
            )
            plist.write_bytes(plistlib.dumps(parsed))
            calls.clear()
            out = StringIO()
            with mock.patch.object(Path, "home", return_value=home), \
                    mock.patch.object(install_coordinator, "run_status", fake_status), \
                    mock.patch.object(install_coordinator, "run_quiet", fake_quiet):
                with redirect_stdout(out):
                    install_coordinator.install(CHECKOUT, False, home)
            uid = os.getuid()
            self.assertEqual(
                [c for c in calls if c[0] == "launchctl"],
                [
                    ["launchctl", "bootout", f"gui/{uid}/dev.coordinator.turncap"],
                    ["launchctl", "print", f"gui/{uid}/dev.coordinator.turncap"],
                    ["launchctl", "bootstrap", f"gui/{uid}", str(plist)],
                ],
            )
            self.assertIn("Reloaded the launchd job dev.coordinator.turncap", out.getvalue())

    def test_an_unchanged_plist_leaves_every_job_running(self):
        with temp_home() as td:
            home = Path(td)
            calls: list[list[str]] = []
            fake_status, fake_quiet = self.launcher(calls)
            with mock.patch.object(install_coordinator, "run_status", fake_status), \
                    mock.patch.object(install_coordinator, "run_quiet", fake_quiet):
                with redirect_stdout(StringIO()):
                    install_coordinator.install(CHECKOUT, False, home)
            calls.clear()
            with mock.patch.object(Path, "home", return_value=home), \
                    mock.patch.object(install_coordinator, "run_status", fake_status), \
                    mock.patch.object(install_coordinator, "run_quiet", fake_quiet):
                with redirect_stdout(StringIO()):
                    install_coordinator.install(CHECKOUT, False, home)
            self.assertEqual([c for c in calls if c[0] == "launchctl"], [])

    def test_a_refused_reload_is_reported_with_the_text_launchctl_wrote(self):
        with temp_home() as td:
            home = Path(td)
            calls: list[list[str]] = []

            def fake_status(argv, *, capture_error=None):
                calls.append(list(argv))
                if argv[1] == "bootout":
                    if capture_error is not None:
                        capture_error.append("Boot-out failed: 5: Input/output error")
                    return 5
                if argv[1] == "list":
                    return 0
                return 0

            with mock.patch.object(install_coordinator, "run_status", fake_status):
                note = install_coordinator.reload_job(
                    "dev.coordinator.turncap", home / "x.plist", os.getuid()
                )
            self.assertIn("Refused to reload", note)
            self.assertIn("Input/output error", note)
            self.assertEqual([c[1] for c in calls], ["bootout", "list"])

    def test_a_refused_bootstrap_is_reported_and_the_job_is_said_to_be_down(self):
        with temp_home() as td:
            home = Path(td)
            calls: list[list[str]] = []

            def fake_status(argv, *, capture_error=None):
                calls.append(list(argv))
                if argv[1] == "bootstrap":
                    if capture_error is not None:
                        capture_error.append(
                            "Bootstrap failed: 5: Input/output error"
                        )
                    return 5
                if argv[1] == "print":
                    return 1
                if argv[1] == "list":
                    return 1
                return 0

            with mock.patch.object(install_coordinator, "run_status", fake_status):
                note = install_coordinator.reload_job(
                    "dev.coordinator.turncap", home / "x.plist", os.getuid()
                )
            self.assertIn("Refused to reload", note)
            self.assertIn("Input/output error", note)
            self.assertIn("not loaded now", note)

    def test_a_job_launchd_loaded_itself_counts_as_reloaded(self):
        with temp_home() as td:
            home = Path(td)

            def fake_status(argv, *, capture_error=None):
                if argv[1] == "bootstrap":
                    if capture_error is not None:
                        capture_error.append(
                            "Bootstrap failed: 37: Operation already in progress"
                        )
                    return 37
                if argv[1] == "print":
                    return 1
                if argv[1] == "list":
                    return 0
                return 0

            with mock.patch.object(install_coordinator, "run_status", fake_status):
                note = install_coordinator.reload_job(
                    "dev.coordinator.turncap", home / "x.plist", os.getuid()
                )
            self.assertIn("Reloaded the launchd job dev.coordinator.turncap", note)
            self.assertIn("launchd had loaded the new plist itself", note)


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


class TestLocalBoardConfig(unittest.TestCase):
    """The installed board config belongs to the machine.

    The policy the coordinator runs with is decided on the Mac, so the
    installed copy is the live file, a local policy edit is not installed
    drift and an install never writes over it (mac-ops #473)."""

    def test_the_board_config_is_seeded_when_the_machine_has_none(self):
        with temp_home() as td:
            home = Path(td)
            with redirect_stdout(StringIO()):
                install_coordinator.install(CHECKOUT, False, home)
            installed = home / ".coordinator/tickets.json"
            self.assertEqual(
                installed.read_bytes(),
                (CHECKOUT / "coordinator/config/tickets.json").read_bytes(),
            )

    def test_an_installed_board_config_is_never_written_over(self):
        with temp_home() as td:
            home = Path(td)
            installed = home / ".coordinator/tickets.json"
            installed.parent.mkdir(parents=True, exist_ok=True)
            edited = '{"repos": {"digitized/Concerning": {"key": "NING"}}}\n'
            installed.write_text(edited)
            with redirect_stdout(StringIO()):
                install_coordinator.install(CHECKOUT, False, home)
            self.assertEqual(installed.read_text(), edited)

    def test_a_local_policy_edit_is_not_installed_drift(self):
        with temp_home() as td:
            home = Path(td)
            installed = home / ".coordinator/tickets.json"
            installed.parent.mkdir(parents=True, exist_ok=True)
            installed.write_text('{"repos": {}}\n')
            differs = [str(t) for t, _, _ in install_coordinator.changes(CHECKOUT, home)]
            self.assertNotIn(str(installed), differs)

    def test_a_machine_without_the_board_config_is_still_a_difference(self):
        with temp_home() as td:
            home = Path(td)
            differs = [str(t) for t, _, _ in install_coordinator.changes(CHECKOUT, home)]
            self.assertIn(str(home / ".coordinator/tickets.json"), differs)

    def test_the_repository_board_config_carries_no_merge_policy(self):
        config = json.loads((CHECKOUT / "coordinator/config/tickets.json").read_text())
        for repo, settings in config["repos"].items():
            self.assertNotIn("merge", settings, repo)


class TestBuilderPromptRules(unittest.TestCase):
    """The builder prompt is the installed agent rules file (mac-ops #506).

    The coordinator prepends the installed rules to every ticket brief, so a
    rule the builders need has to be in the file the installer writes."""

    def test_the_installed_builder_prompt_carries_both_new_rules(self):
        with temp_home() as td:
            home = Path(td)
            with redirect_stdout(StringIO()):
                install_coordinator.install(CHECKOUT, False, home)
            prompt = (home / ".coordinator/AGENT-RULES.md").read_text()
        self.assertIn("shared helper until the third repeat", prompt)
        self.assertIn("tidy commit never changes behavior", prompt)

    def test_the_repository_rules_are_the_source_of_the_installed_prompt(self):
        source = (CHECKOUT / "coordinator/config/AGENT-RULES.md").read_text()
        plan = {
            target: source_path
            for source_path, target, _mode in install_coordinator.plan(CHECKOUT, Path("/Users/example"))
        }
        self.assertEqual(
            plan[Path("/Users/example/.coordinator/AGENT-RULES.md")],
            CHECKOUT / "coordinator/config/AGENT-RULES.md",
        )
        self.assertIn("shared helper until the third repeat", source)
        self.assertIn("tidy commit never changes behavior", source)


class TestReviewerPromptSmellCards(unittest.TestCase):
    """The reviewer prompt is the installed reviewer brief (mac-ops #503).

    The five smell cards from refactor-eval-factory have to be in the
    file the installer writes, and the MIT notice has to travel with
    them."""

    CARDS = (
        "bloated test setup",
        "dead code and leftovers",
        "hardwired dependencies",
        "implementation-coupled tests",
        "toothless tests",
    )

    def test_the_installed_reviewer_prompt_lists_the_five_cards(self):
        with temp_home() as td:
            home = Path(td)
            with redirect_stdout(StringIO()):
                install_coordinator.install(CHECKOUT, False, home)
            prompt = (home / ".coordinator/agents/code-reviewer.md").read_text()
        for card in self.CARDS:
            self.assertIn(card, prompt.lower())

    def test_the_installed_reviewer_prompt_carries_the_attribution(self):
        with temp_home() as td:
            home = Path(td)
            with redirect_stdout(StringIO()):
                install_coordinator.install(CHECKOUT, False, home)
            prompt = (home / ".coordinator/agents/code-reviewer.md").read_text()
        self.assertIn("refactor-eval-factory", prompt)
        self.assertIn("MIT License", prompt)
        self.assertIn("Copyright (c) 2026 Render Services, Inc.", prompt)

    def test_the_repository_prompt_is_the_source_of_the_installed_one(self):
        source = (CHECKOUT / "coordinator/config/agents/code-reviewer.md").read_text()
        plan = {
            target: source_path
            for source_path, target, _mode in install_coordinator.plan(CHECKOUT, Path("/Users/example"))
        }
        self.assertEqual(
            plan[Path("/Users/example/.coordinator/agents/code-reviewer.md")],
            CHECKOUT / "coordinator/config/agents/code-reviewer.md",
        )
        for card in self.CARDS:
            self.assertIn(card, source.lower())


class TestMainSourcePin(unittest.TestCase):
    """The installer only accepts clean canonical main that matches origin/main."""

    def pin(self, overrides=None):
        answers = dict(GIT_ANSWERS)
        answers.update(overrides or {})
        with mock.patch.object(subprocess, "check_output", side_effect=fake_git(answers)):
            return install_coordinator.require_main_source(CHECKOUT)

    def test_clean_main_is_pinned_to_its_fetched_sha(self):
        self.assertEqual(self.pin(), "a" * 40)

    def test_a_linked_worktree_is_refused(self):
        with self.assertRaises(RuntimeError) as caught:
            self.pin({("rev-parse", "--path-format=absolute", "--git-common-dir"): "/tmp/elsewhere/.git"})
        self.assertIn("canonical checkout", str(caught.exception))

    def test_a_branch_other_than_main_is_refused(self):
        with self.assertRaises(RuntimeError) as caught:
            self.pin({("symbolic-ref", "--short", "HEAD"): "feature/pin"})
        self.assertIn("branch main", str(caught.exception))

    def test_a_dirty_checkout_is_refused(self):
        with self.assertRaises(RuntimeError) as caught:
            self.pin({("status", "--porcelain", "--untracked-files=all"): " M install_coordinator.py"})
        self.assertIn("clean checkout", str(caught.exception))

    def test_a_stale_main_is_refused(self):
        with self.assertRaises(RuntimeError) as caught:
            self.pin({("rev-parse", "refs/remotes/origin/main"): "b" * 40})
        self.assertIn("HEAD matching fetched origin/main", str(caught.exception))

    def test_the_receipt_records_the_pinned_source_sha(self):
        with temp_home() as td:
            home = Path(td)
            with redirect_stdout(StringIO()):
                install_coordinator.install(CHECKOUT, False, home)
            receipt = json.loads(
                (home / ".local/state/mac-ops" / install_coordinator.RECEIPT_NAME).read_text()
            )
            self.assertEqual(receipt["source_sha"], "a" * 40)


if __name__ == "__main__":
    unittest.main()
