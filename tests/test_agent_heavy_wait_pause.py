import os
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent_heavy_wait_pause as pause
import heavy
import install


class AgentHeavyWaitPauseTests(unittest.TestCase):
    def test_busy_when_foreground_command(self):
        info = {"foreground_processes": [{"pid": 99, "cmdline": "/usr/bin/git status"}]}
        self.assertEqual(pause._agent_busy(info, []), "foreground-command")

    def test_busy_when_python_script(self):
        info = {
            "foreground_processes": [
                {"pid": 99, "cmdline": "/usr/bin/python3 compute.py"},
            ]
        }
        self.assertEqual(pause._agent_busy(info, []), "foreground-command")

    def test_not_busy_for_cursor_agent_foreground(self):
        info = {
            "foreground_processes": [
                {
                    "pid": 99,
                    "cmdline": "Python /Users/me/.local/bin/cursor-agent --yolo",
                },
            ]
        }
        self.assertIsNone(pause._agent_busy(info, []))

    def test_critical_incomplete_census_holds_state(self):
        state = {
            "schema": pause.STATE_SCHEMA,
            "boot_id": "42",
            "paused": {"mac-ops/1": {"processes": [{"pid": 1}]}},
            "resume_pending": [],
        }
        new_state, summary = pause.tick(
            heavy_mod=heavy,
            boot_id="42",
            agent_census={"schema": 1, "complete": False, "agents": []},
            admission_active=[],
            state=state,
            critical_pressure=True,
        )
        self.assertEqual(summary["action"], "hold")
        self.assertIn("mac-ops/1", new_state["paused"])

    def test_failed_resume_kept_pending(self):
        calls = {"n": 0}

        def fake_signal(identities, signum, deps):
            if signum == signal.SIGCONT and calls["n"] == 0:
                calls["n"] += 1
                return [], list(identities)
            return list(identities), []

        original = heavy.signal_verified_processes
        heavy.signal_verified_processes = fake_signal
        try:
            identity = {
                "pid": 100,
                "start": "1",
                "uid": os.getuid(),
                "boot_id": "42",
                "task_key": "board:mac-ops/1",
            }
            state = {
                "schema": pause.STATE_SCHEMA,
                "boot_id": "42",
                "paused": {"mac-ops/1": {"processes": [identity]}},
                "resume_pending": [],
            }
            cleared, info = pause.resume_all(
                state,
                heavy_mod=heavy,
                boot_id="42",
                deps=heavy.SupervisorDeps(),
                reason="test",
            )
            self.assertEqual(info["failed"], [identity])
            self.assertEqual(cleared["resume_pending"], [identity])
            cleared, info = pause.resume_all(
                cleared,
                heavy_mod=heavy,
                boot_id="42",
                deps=heavy.SupervisorDeps(),
                reason="retry",
            )
            self.assertEqual(info["resumed"], [identity])
            self.assertEqual(cleared.get("resume_pending"), [])
        finally:
            heavy.signal_verified_processes = original

    def test_tick_pauses_with_verified_identities(self):
        signals = []

        def fake_signal(identities, signum, deps):
            for identity in identities:
                signals.append((identity["pid"], signum))
            return list(identities), []

        table = {
            100: heavy.ProcessInfo(
                pid=100,
                ppid=1,
                pgid=100,
                uid=os.getuid(),
                start_token="s100",
                start_epoch=1.0,
                state="S",
            ),
            150: heavy.ProcessInfo(
                pid=150,
                ppid=100,
                pgid=150,
                uid=os.getuid(),
                start_token="s150",
                start_epoch=1.0,
                state="S",
            ),
        }
        original_signal = heavy.signal_verified_processes
        original_table = heavy.process_table
        heavy.signal_verified_processes = fake_signal
        heavy.process_table = lambda: table
        registry_calls = []

        class FakeRegistry:
            def __init__(self, _path):
                pass

            def lock(self, exclusive=False):
                return _NullContext()

            def queue_records(self):
                return [
                    {
                        "queue_id": "q1",
                        "task_key": "board:mac-ops/1",
                        "process": {
                            "pid": 150,
                            "uid": os.getuid(),
                            "start": "s150",
                            "boot_id": "42",
                        },
                    }
                ]

            def records(self):
                return []

            def update_queue(self, queue_id, mutator):
                registry_calls.append(queue_id)

        heavy.Registry = FakeRegistry
        try:
            census = {
                "schema": 1,
                "complete": True,
                "agents": [
                    {
                        "id": "mac-ops/1",
                        "pids": [100, 150],
                        "process_info": {
                            "foreground_processes": [
                                {"pid": 100, "cmdline": "Python cursor-agent"},
                            ]
                        },
                    }
                ],
            }
            _state, summary = pause.tick(
                heavy_mod=heavy,
                boot_id="42",
                agent_census=census,
                admission_active=[{"id": "mac-ops/1", "stage": "working"}],
                state=None,
                critical_pressure=True,
            )
            self.assertIn("mac-ops/1", summary["paused_tasks"])
            self.assertTrue(
                any(pid == 100 and signum == signal.SIGSTOP for pid, signum in signals)
            )
            self.assertFalse(any(pid == 150 for pid, _ in signals))
            self.assertEqual(registry_calls, ["q1"])
        finally:
            heavy.signal_verified_processes = original_signal
            heavy.process_table = original_table

    def test_multi_agent_pause_and_resume_on_admit(self):
        signals: list[tuple[int, int]] = []

        def fake_signal(identities, signum, deps):
            for identity in identities:
                signals.append((identity["pid"], signum))
            return list(identities), []

        def make_table(agent_pid: int, sup_pid: int) -> dict:
            return {
                agent_pid: heavy.ProcessInfo(
                    pid=agent_pid,
                    ppid=1,
                    pgid=agent_pid,
                    uid=os.getuid(),
                    start_token=f"s{agent_pid}",
                    start_epoch=1.0,
                    state="S",
                ),
                sup_pid: heavy.ProcessInfo(
                    pid=sup_pid,
                    ppid=agent_pid,
                    pgid=sup_pid,
                    uid=os.getuid(),
                    start_token=f"s{sup_pid}",
                    start_epoch=1.0,
                    state="S",
                ),
            }

        table = {}
        for agent_pid, sup_pid in ((100, 150), (200, 250), (300, 350)):
            table.update(make_table(agent_pid, sup_pid))

        queue_rows = [
            {
                "queue_id": "q1",
                "task_key": "board:mac-ops/1",
                "process": {
                    "pid": 150,
                    "uid": os.getuid(),
                    "start": "s150",
                    "boot_id": "42",
                },
            },
            {
                "queue_id": "q2",
                "task_key": "board:mac-ops/2",
                "process": {
                    "pid": 250,
                    "uid": os.getuid(),
                    "start": "s250",
                    "boot_id": "42",
                },
            },
            {
                "queue_id": "q3",
                "task_key": "board:mac-ops/3",
                "process": {
                    "pid": 350,
                    "uid": os.getuid(),
                    "start": "s350",
                    "boot_id": "42",
                },
            },
        ]
        heavy_records: list[dict] = []

        class FakeRegistry:
            def __init__(self, _path):
                pass

            def lock(self, exclusive=False):
                return _NullContext()

            def queue_records(self):
                return list(queue_rows)

            def records(self):
                return list(heavy_records)

            def update_queue(self, queue_id, mutator):
                return None

        def agent_row(task_num: int, agent_pid: int, sup_pid: int) -> dict:
            return {
                "id": f"mac-ops/{task_num}",
                "pids": [agent_pid, sup_pid],
                "process_info": {
                    "foreground_processes": [
                        {"pid": agent_pid, "cmdline": "Python cursor-agent"},
                    ]
                },
            }

        census = {
            "schema": 1,
            "complete": True,
            "agents": [
                agent_row(1, 100, 150),
                agent_row(2, 200, 250),
                agent_row(3, 300, 350),
            ],
        }
        admission = [{"id": f"mac-ops/{n}", "stage": "working"} for n in (1, 2, 3)]

        original_signal = heavy.signal_verified_processes
        original_table = heavy.process_table
        original_registry = heavy.Registry
        heavy.signal_verified_processes = fake_signal
        heavy.process_table = lambda: table
        heavy.Registry = FakeRegistry
        try:
            state, summary1 = pause.tick(
                heavy_mod=heavy,
                boot_id="42",
                agent_census=census,
                admission_active=admission,
                state=None,
                critical_pressure=False,
            )
            self.assertEqual(len(summary1["paused_tasks"]), 3)
            stops = [pid for pid, sig in signals if sig == signal.SIGSTOP]
            self.assertEqual(sorted(stops), [100, 200, 300])

            heavy_records.append(
                {
                    "state": "running",
                    "task_key": "board:mac-ops/2",
                    "supervisor": {
                        "pid": 250,
                        "uid": os.getuid(),
                        "start": "s250",
                        "boot_id": "42",
                    },
                }
            )
            state2, summary2 = pause.tick(
                heavy_mod=heavy,
                boot_id="42",
                agent_census=census,
                admission_active=admission,
                state=state,
                critical_pressure=False,
            )
            self.assertIn("mac-ops/2", summary2["resumed_tasks"])
            self.assertIn("mac-ops/1", state2["paused"])
            self.assertIn("mac-ops/3", state2["paused"])
            self.assertNotIn("mac-ops/2", state2["paused"])
            conts = [pid for pid, sig in signals if sig == signal.SIGCONT]
            self.assertIn(200, conts)
        finally:
            heavy.signal_verified_processes = original_signal
            heavy.process_table = original_table
            heavy.Registry = original_registry


class InstallReleaseTests(unittest.TestCase):
    def test_release_includes_pause_module(self):
        self.assertIn("agent_heavy_wait_pause.py", install.FILES)
        checkout = ROOT
        release = Path(tempfile.mkdtemp(prefix="mo23-release-"))
        try:
            for name in install.FILES:
                shutil.copy2(checkout / name, release / name)
            proc = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(release / "board_governor.py"),
                    "status",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
                cwd=str(release),
            )
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        finally:
            shutil.rmtree(release)


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


if __name__ == "__main__":
    unittest.main()
