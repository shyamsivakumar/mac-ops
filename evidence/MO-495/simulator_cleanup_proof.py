"""Proof for #495: a simulator job's device is shut down when the job ends.

Run from the worktree root:

    python3 evidence/MO-495/simulator_cleanup_proof.py

It boots a simulator, runs the same cleanup path a heavy xcodebuild job runs
when it ends, and shows the device is shut down and the simulator process
count returns to its baseline.
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import heavy  # noqa: E402


def simulator_process_count():
    """Return the number of running simulator runtime processes."""
    output = subprocess.run(
        ["/bin/ps", "-axo", "command="], capture_output=True, text=True, check=True
    ).stdout
    return sum(1 for line in output.splitlines() if ".simruntime" in line)


def shutdown_devices():
    """Return the simulators that can be booted for this proof."""
    output = subprocess.run(
        ["/usr/bin/xcrun", "simctl", "list", "devices", "--json"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    import json

    devices = json.loads(output)["devices"]
    choices = []
    for runtime, rows in devices.items():
        for row in rows:
            if row.get("isAvailable") and row.get("state") == "Shutdown":
                choices.append((runtime, row["udid"], row.get("name")))
    return choices


def main():
    before_devices = heavy.simulator_booted_devices()
    baseline = simulator_process_count()
    print("booted devices before:", sorted(before_devices))
    print("simulator process count before:", baseline)
    choices = shutdown_devices()
    if not choices:
        print("no simulator can be booted on this host")
        return 1
    runtime, udid, name = choices[0]
    started_at = time.time()
    print("booting", name, udid, "on", runtime)
    subprocess.run(
        ["/usr/bin/xcrun", "simctl", "boot", udid], check=True, capture_output=True
    )
    deadline = time.time() + 120
    while time.time() < deadline:
        if udid in heavy.simulator_booted_devices():
            break
        time.sleep(1.0)
    assert udid in heavy.simulator_booted_devices(), "the device did not boot"
    print("booted devices while the job runs:", sorted(heavy.simulator_booted_devices()))
    print("simulator process count while the job runs:", simulator_process_count())
    record = {
        "job_id": "0" * 31 + "2",
        "task_id": "proof-simulator-job",
        "simulators": {"booted": sorted(before_devices), "started_at": started_at},
    }
    stopped = heavy.shutdown_simulators_booted_by_job(record)
    print("devices shut down when the job ended:", stopped)
    assert stopped == [udid], stopped
    deadline = time.time() + 60
    while time.time() < deadline:
        if udid not in heavy.simulator_booted_devices():
            break
        time.sleep(1.0)
    after_devices = heavy.simulator_booted_devices()
    after = simulator_process_count()
    print("booted devices after:", sorted(after_devices))
    print("simulator process count after:", after)
    print("baseline was:", baseline)
    assert udid not in after_devices
    return 0


if __name__ == "__main__":
    sys.exit(main())
