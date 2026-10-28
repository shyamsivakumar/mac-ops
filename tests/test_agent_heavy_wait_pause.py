import os
import signal
import unittest
from types import SimpleNamespace

import agent_heavy_wait_pause as pause


class AgentHeavyWaitPauseTests(unittest.TestCase):
    def test_busy_when_foreground_command(self):
        info = {
            "foreground_processes": [
                {"pid": 99, "cmdline": "/usr/bin/git status"},
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

    def test_pause_targets_exclude_supervisor_subtree(self):
        processes = {
            10: SimpleNamespace(ppid=1, pid=10),
            20: SimpleNamespace(ppid=10, pid=20),
            30: SimpleNamespace(ppid=20, pid=30),
        }
        descendants = pause._descendant_pids(20, processes)
        self.assertEqual(descendants, {30})

    def test_tick_pauses_and_resumes(self):
        signals = []

        def signal_pid(pid, signum):
            signals.append((pid, signum))

        table = {
            100: SimpleNamespace(uid=os.getuid(), state="S", pid=100, ppid=1),
            200: SimpleNamespace(uid=os.getuid(), state="S", pid=200, ppid=150),
            150: SimpleNamespace(uid=os.getuid(), state="S", pid=150, ppid=100),
        }
        heavy_mod = SimpleNamespace(
            process_table=lambda: table,
            _identity_matches=lambda info, identity: (
                info is not None and info.pid == identity.get("pid")
            ),
            _record_live=lambda record, _table: (
                record.get("state") == "running",
                True,
            ),
            Registry=lambda _path: SimpleNamespace(
                lock=lambda exclusive=False: _NullContext(),
                queue_records=lambda: [
                    {
                        "queue_id": "q1",
                        "task_key": "board:mac-ops/1",
                        "process": {
                            "pid": 150,
                            "uid": os.getuid(),
                            "start": "1",
                            "boot_id": "42",
                        },
                    }
                ],
                records=list,
            ),
            state_directory=lambda: "/tmp/unused",
        )

        census = {
            "schema": 1,
            "complete": True,
            "agents": [
                {
                    "id": "mac-ops/1",
                    "pids": [100, 150, 200],
                    "process_info": {
                        "foreground_processes": [
                            {"pid": 100, "cmdline": "Python cursor-agent"},
                        ]
                    },
                }
            ],
        }
        state, summary = pause.tick(
            heavy_mod=heavy_mod,
            boot_id="42",
            agent_census=census,
            admission_active=[{"id": "mac-ops/1", "stage": "working"}],
            state=None,
            signal_pid=signal_pid,
        )
        self.assertIn("mac-ops/1", summary["paused_tasks"])
        self.assertTrue(
            any(signum == signal.SIGSTOP for _pid, signum in signals if _pid == 100)
        )
        self.assertFalse(any(pid == 150 for pid, _ in signals))

        state, summary = pause.tick(
            heavy_mod=heavy_mod,
            boot_id="42",
            agent_census={"schema": 1, "complete": False, "agents": []},
            admission_active=[],
            state=state,
            signal_pid=signal_pid,
        )
        self.assertEqual(summary["action"], "resume")
        self.assertTrue(
            any(signum == signal.SIGCONT for _pid, signum in signals if _pid == 100)
        )
        self.assertEqual(state["paused"], {})


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


if __name__ == "__main__":
    unittest.main()
