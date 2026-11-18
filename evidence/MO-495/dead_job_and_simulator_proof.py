"""Proof for #495: a dead supervisor frees its slot, and simulator cleanup is safe.

Run from the worktree root:

    python3 evidence/MO-495/dead_job_and_simulator_proof.py

It starts a real supervisor in a temporary registry, kills that supervisor,
shows that the governor reap frees the slot and logs one line, and shows that
the simulator sweep leaves a booted device alone.
"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import heavy  # noqa: E402

CHILD = """
import sys
sys.path.insert(0, {root!r})
import heavy
registry = heavy.Registry({registry!r})
registry.ensure_protocol()
code = heavy.run_supervisor(
    ["/bin/sleep", "300"],
    registry=registry,
    task_key="manual:proof",
    task_id="proof-dead-job",
)
sys.exit(code)
"""


def active_records(registry):
    """Return the records the admission count would see as active."""
    with registry.lock(exclusive=False):
        return [
            row
            for row in registry.records()
            if row.get("state") not in ("complete", "removed")
        ]


def dead_job_proof():
    """Start a job, kill its supervisor, and show the slot is freed."""
    directory = tempfile.mkdtemp(
        prefix="heavy-proof-", dir=str(heavy.state_directory().parent)
    )
    os.chmod(directory, 0o700)
    registry = heavy.Registry(directory)
    registry.ensure_protocol()
    program = CHILD.format(root=str(ROOT), registry=directory)
    child = subprocess.Popen(
        ["/usr/bin/python3", "-c", program],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    supervisor_pid = None
    deadline = time.time() + 30
    while time.time() < deadline:
        rows = active_records(registry)
        if rows:
            supervisor_pid = rows[0]["supervisor"]["pid"]
            break
        time.sleep(0.2)
    assert supervisor_pid is not None, "the job never reserved a slot"
    before = len(active_records(registry))
    os.kill(supervisor_pid, signal.SIGKILL)
    child.wait(timeout=10)
    reaped = heavy.reap_dead_jobs(registry)
    after = len(active_records(registry))
    events = []
    with open(os.path.join(directory, "events.jsonl"), encoding="utf-8") as handle:
        for line in handle:
            events.append(json.loads(line))
    dead = [entry for entry in events if entry["event"] == "job-dead"]
    print("supervisor pid:", supervisor_pid)
    print("active jobs before the kill:", before)
    print("reaped jobs:", [entry["record"]["job_id"] for entry in reaped])
    print("active jobs after the reap:", after)
    print("job-dead log lines:", len(dead))
    print("job-dead log line:", json.dumps(dead[0], sort_keys=True) if dead else None)
    assert before == 1
    assert after == 0
    assert len(dead) == 1
    return True


def simulator_proof():
    """Show that a booted device is never shut down or swept away."""
    booted = heavy.simulator_booted_devices()
    rows = heavy.simulator_process_rows()
    owners = heavy.simulator_device_owners(rows)
    orphan_pids = sorted(pid for pid, udid in owners.items() if udid not in booted)
    print("booted simulator devices:", len(booted))
    print("simulator processes attributed to a device:", len(owners))
    print("simulator processes of a device that is not booted:", len(orphan_pids))
    if not booted:
        print("no simulator is booted on this host; nothing to protect")
        return True
    device = sorted(booted)[0]
    record = {
        "job_id": "0" * 31 + "1",
        "task_id": "proof",
        "simulators": {"booted": sorted(booted), "started_at": time.time()},
    }
    stopped = heavy.shutdown_simulators_booted_by_job(
        record,
        booted_reader=lambda: booted,
        rows_reader=lambda: rows,
    )
    print("devices shut down for a job that booted none:", stopped)
    assert stopped == []
    return True


if __name__ == "__main__":
    dead_job_proof()
    simulator_proof()
    print("proof ok")
