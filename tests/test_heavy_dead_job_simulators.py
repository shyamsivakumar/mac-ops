"""Dead job release and simulator cleanup tests for the heavy supervisor."""
import json
import os
import tempfile
import unittest

import heavy


DEVICE_A = "AAAAAAAA-1111-2222-3333-444444444444"
DEVICE_B = "BBBBBBBB-1111-2222-3333-444444444444"


def launchd_row(pid, udid):
    """Return one launchd_sim process row for a simulator device."""
    return (
        pid,
        1,
        "launchd_sim /Users/test/Library/Developer/CoreSimulator/Devices/"
        + udid
        + "/data/var/run/launchd_bootstrap.plist",
    )


def app_row(pid, ppid):
    """Return one simulator application process row."""
    return (
        pid,
        ppid,
        "/private/var/run/com.apple.iPhoneOS.SimulatorRuntime/iOS 27.0.simruntime/"
        "Contents/Resources/RuntimeRoot/System/Library/Frameworks/Example.framework/"
        "ExampleAgent",
    )


def executables(rows):
    """Return a reader that gives each row's executable the way libproc would."""
    table = {}
    for pid, _, command in rows:
        if command.startswith("launchd_sim"):
            table[pid] = "/Library/Developer/PrivateFrameworks/CoreSimulator.framework/launchd_sim"
        elif command.startswith("/"):
            table[pid] = command
        else:
            table[pid] = "/usr/bin/" + command.split()[0]
    return lambda pid: table.get(pid)


def tail_row(pid, ppid, udid):
    """Return a process row for a tail command that names a device log path."""
    return (
        pid,
        ppid,
        "tail -f /Users/test/Library/Developer/CoreSimulator/Devices/"
        + udid
        + "/data/Library/Logs/CoreSimulator/system.log",
    )


class SimulatorOwnerTests(unittest.TestCase):
    def test_launchd_and_application_processes_share_one_device(self):
        rows = [launchd_row(10, DEVICE_A), app_row(11, 10)]
        owners = heavy.simulator_device_owners(rows, executables(rows))
        self.assertEqual(owners[10], DEVICE_A)
        self.assertEqual(owners[11], DEVICE_A)

    def test_orphan_sweep_stops_only_processes_of_a_device_that_is_not_booted(self):
        rows = [
            launchd_row(10, DEVICE_A),
            app_row(11, 10),
            launchd_row(20, DEVICE_B),
            app_row(21, 20),
        ]
        killed = []
        ticks = [0.0]

        def clock():
            ticks[0] += 1.0
            return ticks[0]

        result = heavy.stop_orphan_simulator_processes(
            booted_reader=lambda: {DEVICE_A: "runtime-a"},
            rows_reader=lambda: rows,
            kill=lambda pid, signum: killed.append((pid, signum)),
            sleep=lambda seconds: None,
            clock=clock,
            identity_reader=lambda pid: (os.getuid(), "1.000000"),
            executable_reader=executables(rows),
        )
        self.assertEqual(result["stopped"], 2)
        self.assertEqual(result["devices"], [DEVICE_B])
        signalled = {pid for pid, signum in killed}
        self.assertEqual(signalled, {20, 21})
        for pid, signum in killed:
            self.assertIn(signum, (heavy.signal.SIGTERM, heavy.signal.SIGKILL))

    def test_a_device_that_starts_booting_while_the_sweep_runs_is_left_alone(self):
        rows = [launchd_row(10, DEVICE_A), app_row(11, 10)]
        killed = []
        readings = [{}, {DEVICE_A: "runtime-a"}]

        def booted_reader():
            return readings.pop(0) if readings else {DEVICE_A: "runtime-a"}

        result = heavy.stop_orphan_simulator_processes(
            booted_reader=booted_reader,
            rows_reader=lambda: rows,
            kill=lambda pid, signum: killed.append((pid, signum)),
            sleep=lambda seconds: None,
            clock=lambda: 0.0,
            identity_reader=lambda pid: (os.getuid(), "1.000000"),
            executable_reader=executables(rows),
        )
        self.assertEqual(result["stopped"], 0)
        self.assertEqual(killed, [])

    def test_a_process_that_only_names_a_device_path_is_not_touched(self):
        rows = [launchd_row(10, DEVICE_B), tail_row(30, 1, DEVICE_B)]
        killed = []
        result = heavy.stop_orphan_simulator_processes(
            booted_reader=lambda: {},
            rows_reader=lambda: rows,
            kill=lambda pid, signum: killed.append((pid, signum)),
            sleep=lambda seconds: None,
            clock=lambda: 0.0,
            identity_reader=lambda pid: (os.getuid(), "1.000000"),
            executable_reader=executables(rows),
        )
        self.assertEqual(result["stopped"], 1)
        self.assertEqual({pid for pid, _ in killed}, {10})

    def test_orphan_sweep_leaves_a_booted_device_alone(self):
        rows = [launchd_row(10, DEVICE_A), app_row(11, 10)]
        killed = []
        result = heavy.stop_orphan_simulator_processes(
            booted_reader=lambda: {DEVICE_A: "runtime-a"},
            rows_reader=lambda: rows,
            kill=lambda pid, signum: killed.append((pid, signum)),
            sleep=lambda seconds: None,
            clock=lambda: 0.0,
            identity_reader=lambda pid: (os.getuid(), "1.000000"),
            executable_reader=executables(rows),
        )
        self.assertEqual(result["stopped"], 0)
        self.assertEqual(killed, [])

    def test_a_device_that_starts_booting_after_the_first_read_is_left_alone(self):
        rows = [launchd_row(10, DEVICE_A), app_row(11, 10)]
        killed = []
        readings = [{}, {DEVICE_A: "runtime-a"}]

        def booted_reader():
            return readings.pop(0) if readings else {DEVICE_A: "runtime-a"}

        result = heavy.stop_orphan_simulator_processes(
            booted_reader=booted_reader,
            rows_reader=lambda: rows,
            kill=lambda pid, signum: killed.append((pid, signum)),
            sleep=lambda seconds: None,
            clock=lambda: 0.0,
            identity_reader=lambda pid: (os.getuid(), "1.000000"),
            executable_reader=executables(rows),
        )
        self.assertEqual(result["stopped"], 0)
        self.assertEqual(killed, [])

    def test_a_device_that_boots_during_the_term_wait_is_not_sent_sigkill(self):
        rows = [launchd_row(10, DEVICE_A), app_row(11, 10)]
        killed = []
        readings = [{}, {}, {}, {DEVICE_A: "runtime-a"}]
        ticks = [0.0]

        def booted_reader():
            return readings.pop(0) if readings else {DEVICE_A: "runtime-a"}

        def clock():
            ticks[0] += 1.0
            return ticks[0]

        heavy.stop_orphan_simulator_processes(
            booted_reader=booted_reader,
            rows_reader=lambda: rows,
            kill=lambda pid, signum: killed.append((pid, signum)),
            sleep=lambda seconds: None,
            clock=clock,
            identity_reader=lambda pid: (os.getuid(), "1.000000"),
            executable_reader=executables(rows),
        )
        self.assertTrue(killed)
        self.assertEqual({signum for pid, signum in killed}, {heavy.signal.SIGTERM})

    def test_a_process_that_only_names_a_device_path_is_not_a_simulator_process(self):
        rows = [tail_row(30, 500, DEVICE_B)]
        killed = []
        owners = heavy.simulator_device_owners(rows, executables(rows))
        self.assertEqual(owners, {})
        result = heavy.stop_orphan_simulator_processes(
            booted_reader=lambda: {},
            rows_reader=lambda: rows,
            kill=lambda pid, signum: killed.append((pid, signum)),
            sleep=lambda seconds: None,
            clock=lambda: 0.0,
            identity_reader=lambda pid: (os.getuid(), "1.000000"),
            executable_reader=executables(rows),
        )
        self.assertEqual(result["stopped"], 0)
        self.assertEqual(killed, [])

    def test_a_runtime_process_with_no_launchd_above_it_is_an_orphan(self):
        rows = [app_row(40, 1), launchd_row(10, DEVICE_A), app_row(11, 10)]
        killed = []
        ticks = [0.0]

        def clock():
            ticks[0] += 1.0
            return ticks[0]

        result = heavy.stop_orphan_simulator_processes(
            booted_reader=lambda: {DEVICE_A: "runtime-a"},
            rows_reader=lambda: rows,
            kill=lambda pid, signum: killed.append((pid, signum)),
            sleep=lambda seconds: None,
            clock=clock,
            identity_reader=lambda pid: (os.getuid(), "1.000000"),
            executable_reader=executables(rows),
        )
        self.assertEqual(result["stopped"], 1)
        self.assertEqual({pid for pid, signum in killed}, {40})

    def test_a_runtime_process_whose_parent_chain_is_unknown_is_left_alone(self):
        rows = [app_row(40, 999)]
        owners = heavy.simulator_device_owners(rows, executables(rows))
        self.assertEqual(owners, {})

    def test_a_process_that_started_after_the_listing_is_a_reused_pid(self):
        rows = [launchd_row(10, DEVICE_B)]
        killed = []
        result = heavy.stop_orphan_simulator_processes(
            booted_reader=lambda: {},
            rows_reader=lambda: rows,
            kill=lambda pid, signum: killed.append((pid, signum)),
            sleep=lambda seconds: None,
            clock=lambda: 0.0,
            identity_reader=lambda pid: (os.getuid(), "5000.000000"),
            executable_reader=executables(rows),
            epoch_clock=lambda: 4000.0,
        )
        self.assertEqual(result["stopped"], 0)
        self.assertEqual(killed, [])

    def test_a_process_whose_identity_cannot_be_read_is_not_killed(self):
        rows = [launchd_row(10, DEVICE_B)]
        killed = []
        result = heavy.stop_orphan_simulator_processes(
            booted_reader=lambda: {},
            rows_reader=lambda: rows,
            kill=lambda pid, signum: killed.append((pid, signum)),
            sleep=lambda seconds: None,
            clock=lambda: 0.0,
            identity_reader=lambda pid: None,
            executable_reader=executables(rows),
        )
        self.assertEqual(result["stopped"], 0)
        self.assertEqual(killed, [])


class SimulatorShutdownTests(unittest.TestCase):
    def test_job_shuts_down_the_devices_it_booted(self):
        rows = [launchd_row(10, DEVICE_A), launchd_row(20, DEVICE_B)]
        stopped = []
        record = {
            "job_id": "a" * 32,
            "task_id": "task",
            "simulators": {"booted": [], "started_at": 1000.0},
        }
        result = heavy.shutdown_simulators_booted_by_job(
            record,
            booted_reader=lambda: {DEVICE_A: "runtime-a", DEVICE_B: "runtime-b"},
            rows_reader=lambda: rows,
            epochs_reader=lambda table: {DEVICE_A: 1100.0, DEVICE_B: 1100.0},
            shutdown=lambda udid: stopped.append(udid) or True,
        )
        self.assertEqual(result, [DEVICE_A, DEVICE_B])
        self.assertEqual(stopped, [DEVICE_A, DEVICE_B])

    def test_device_booted_before_the_job_stays_on(self):
        rows = [launchd_row(10, DEVICE_A)]
        stopped = []
        record = {
            "job_id": "b" * 32,
            "task_id": "task",
            "simulators": {"booted": [DEVICE_A], "started_at": 1000.0},
        }
        result = heavy.shutdown_simulators_booted_by_job(
            record,
            booted_reader=lambda: {DEVICE_A: "runtime-a"},
            rows_reader=lambda: rows,
            epochs_reader=lambda table: {DEVICE_A: 900.0},
            shutdown=lambda udid: stopped.append(udid) or True,
        )
        self.assertEqual(result, [])
        self.assertEqual(stopped, [])

    def test_device_another_running_job_may_use_stays_on(self):
        rows = [launchd_row(10, DEVICE_A), launchd_row(20, DEVICE_B)]
        stopped = []
        record = {
            "job_id": "c" * 32,
            "task_id": "task",
            "simulators": {"booted": [], "started_at": 1000.0},
        }
        other = {
            "job_id": "d" * 32,
            "state": "running",
            "command_basename": "xcodebuild",
            "simulators": {"booted": [DEVICE_B], "started_at": 1150.0},
        }
        result = heavy.shutdown_simulators_booted_by_job(
            record,
            other_records=[other],
            booted_reader=lambda: {DEVICE_A: "runtime-a", DEVICE_B: "runtime-b"},
            rows_reader=lambda: rows,
            epochs_reader=lambda table: {DEVICE_A: 1100.0, DEVICE_B: 1100.0},
            shutdown=lambda udid: stopped.append(udid) or True,
        )
        self.assertEqual(result, [DEVICE_A])
        self.assertEqual(stopped, [DEVICE_A])

    def test_cleanup_waits_for_a_simulator_job_that_was_running_when_the_device_booted(self):
        rows = [launchd_row(10, DEVICE_A)]
        stopped = []
        record = {
            "job_id": "e" * 32,
            "task_id": "task",
            "simulators": {"booted": [], "started_at": 1000.0},
        }
        other = {
            "job_id": "f" * 32,
            "state": "running",
            "command_basename": "xcodebuild",
            "simulators": {"booted": [], "started_at": 900.0},
        }
        result = heavy.shutdown_simulators_booted_by_job(
            record,
            other_records=[other],
            booted_reader=lambda: {DEVICE_A: "runtime-a"},
            rows_reader=lambda: rows,
            epochs_reader=lambda table: {DEVICE_A: 1100.0},
            shutdown=lambda udid: stopped.append(udid) or True,
        )
        self.assertEqual(result, [])
        self.assertEqual(stopped, [])

    def test_cleanup_stops_when_the_competing_jobs_cannot_be_read(self):
        rows = [launchd_row(10, DEVICE_A)]
        stopped = []
        record = {
            "job_id": "0" * 31 + "3",
            "task_id": "task",
            "simulators": {"booted": [], "started_at": 1000.0},
        }

        def failing_reader():
            raise RuntimeError("registry unavailable")

        result = heavy.shutdown_simulators_booted_by_job(
            record,
            other_records_reader=failing_reader,
            booted_reader=lambda: {DEVICE_A: "runtime-a"},
            rows_reader=lambda: rows,
            epochs_reader=lambda table: {DEVICE_A: 1100.0},
            shutdown=lambda udid: stopped.append(udid) or True,
        )
        self.assertEqual(result, [])
        self.assertEqual(stopped, [])


class SimulatorLockTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="heavy-sim-lock-test-")
        os.chmod(self.directory, 0o700)
        self.registry = heavy.Registry(self.directory)
        self.registry.ensure_protocol()
        self.original_timeout = heavy.SIMULATOR_LOCK_TIMEOUT
        heavy.SIMULATOR_LOCK_TIMEOUT = 0.2
        self.addCleanup(setattr, heavy, "SIMULATOR_LOCK_TIMEOUT", self.original_timeout)

    def test_a_simulator_job_without_a_snapshot_keeps_every_device_on(self):
        rows = [launchd_row(10, DEVICE_A)]
        stopped = []
        record = {
            "job_id": "7" * 32,
            "task_id": "task",
            "simulators": {"booted": [], "started_at": 1000.0},
        }
        other = {"job_id": "8" * 32, "state": "starting", "command_basename": "xcodebuild"}
        result = heavy.shutdown_simulators_booted_by_job(
            record,
            other_records=[other],
            booted_reader=lambda: {DEVICE_A: "runtime-a"},
            rows_reader=lambda: rows,
            epochs_reader=lambda table: {DEVICE_A: 1100.0},
            shutdown=lambda udid: stopped.append(udid) or True,
        )
        self.assertEqual(result, [])
        self.assertEqual(stopped, [])

    def test_cleanup_shuts_nothing_down_while_another_job_holds_the_simulator_lock(self):
        record = {
            "job_id": "9" * 32,
            "task_id": "task",
            "simulators": {"booted": [], "started_at": 1000.0},
        }
        shutdowns = []
        original = heavy._simulator_shutdown
        heavy._simulator_shutdown = lambda udid: shutdowns.append(udid) or True
        self.addCleanup(setattr, heavy, "_simulator_shutdown", original)
        with self.registry.lock(name=heavy.SIMULATOR_LOCK_NAME):
            result = heavy._cleanup_job_simulators(self.registry, record)
        self.assertEqual(result, [])
        self.assertEqual(shutdowns, [])

    def test_a_job_that_cannot_take_the_simulator_lock_records_no_snapshot(self):
        job = {
            "schema": 1,
            "clock": "CLOCK_MONOTONIC",
            "job_id": "a1" * 16,
            "uid": os.getuid(),
            "task_key": "manual:sim",
            "task_id": "sim",
            "command_basename": "xcodebuild",
            "role": "ordinary",
            "created_ns": 1,
            "state": "starting",
            "supervisor": {
                "pid": os.getpid(),
                "start": "1.000000",
                "uid": os.getuid(),
                "boot_id": "12345",
                "task_key": "manual:sim",
            },
            "workload": None,
        }
        self.registry.create(job)
        with self.registry.lock(name=heavy.SIMULATOR_LOCK_NAME):
            heavy._attach_simulator_state(
                self.registry, job["job_id"], "xcodebuild", ["xcodebuild"]
            )
        self.assertNotIn("simulators", self.registry._read_record(job["job_id"]))


class DeadJobReapTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="heavy-reap-test-")
        os.chmod(self.directory, 0o700)
        self.registry = heavy.Registry(self.directory)
        self.registry.ensure_protocol()
        table = heavy.process_table()
        info = table[os.getpid()]
        self.live = {
            "schema": 1,
            "clock": "CLOCK_MONOTONIC",
            "job_id": "1" * 32,
            "uid": os.getuid(),
            "task_key": "manual:live",
            "task_id": "live",
            "command_basename": "sleep",
            "role": "ordinary",
            "created_ns": 1,
            "state": "running",
            "supervisor": {
                "pid": info.pid,
                "start": info.start_token,
                "uid": info.uid,
                "boot_id": "12345",
                "task_key": "manual:live",
            },
            "workload": None,
        }
        self.dead = {
            "schema": 1,
            "clock": "CLOCK_MONOTONIC",
            "job_id": "2" * 32,
            "uid": os.getuid(),
            "task_key": "manual:dead",
            "task_id": "dead",
            "command_basename": "sleep",
            "role": "ordinary",
            "created_ns": 2,
            "state": "starting",
            "supervisor": {
                "pid": 999999,
                "start": "1700000000.000000",
                "uid": os.getuid(),
                "boot_id": "12345",
                "task_key": "manual:dead",
            },
            "workload": None,
        }
        self.registry.create(self.live)
        self.registry.create(self.dead)

    def test_dead_supervisor_frees_its_slot_and_logs_one_line(self):
        reaped = heavy.reap_dead_jobs(
            self.registry, table_reader=heavy.process_table, boot_reader=lambda: "12345"
        )
        self.assertEqual([entry["record"]["job_id"] for entry in reaped], ["2" * 32])
        remaining = [row["job_id"] for row in self.registry.records()]
        self.assertEqual(remaining, ["1" * 32])
        events = []
        with open(
            os.path.join(self.directory, "events.jsonl"), encoding="utf-8"
        ) as handle:
            for line in handle:
                events.append(json.loads(line))
        dead_events = [entry for entry in events if entry["event"] == "job-dead"]
        self.assertEqual(len(dead_events), 1)
        self.assertEqual(dead_events[0]["detail"], "supervisor-gone; slot freed")

    def test_live_supervisor_keeps_its_slot(self):
        heavy.reap_dead_jobs(
            self.registry, table_reader=heavy.process_table, boot_reader=lambda: "12345"
        )
        record = self.registry._read_record("1" * 32)
        self.assertEqual(record["state"], "running")


if __name__ == "__main__":
    unittest.main()
