#!/usr/bin/env python3
"""Proof for MO-1056: the watchdog reads the job's real state, not its log age.

Scenario one: a stale gatekeep log, an empty gate queue and a gatekeep job
that launchd still holds. The watchdog must print no WATCHDOG line and must
not write the factory-watchdog item.

Scenario two: the same stale log with the gatekeep job stopped. The watchdog
must alarm, and the alarm must name the stopped job.

The proof never touches the live board file, the live logs or the running
jobs. The decisions file is a copy, the log is a copy with an old mtime, and
the stopped job is a stub. The live launchd state is read, never changed.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "coordinator/overnight"))

import lane_driver as lane  # noqa: E402

GATEKEEP = "dev.coordinator.gatekeep"
STALE_MINUTES = 200
LIMIT = 120


def load_state(label):
    """Return the live launchd state of one job, read only."""
    return lane.launchd_state(label)


def run_pass(decisions_path, log_path):
    """Run one watchdog pass against the given files and return (output, items)."""
    lane.DECISIONS_PATH = str(decisions_path)
    lane.WATCH = {"gatekeep": (str(log_path), LIMIT, GATEKEEP)}
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        lane.watchdog()
    items = json.loads(decisions_path.read_text())["items"]
    return buffer.getvalue(), items


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        decisions = root / "decisions.json"
        decisions.write_text(json.dumps({"items": []}, indent=1))
        log = root / "gatekeep.log"
        log.write_text("")
        old = time.time() - STALE_MINUTES * 60
        os.utime(log, (old, old))

        live = load_state(GATEKEEP)
        print(f"live launchd state of {GATEKEEP}: {live}")
        print(f"gatekeep log age: {STALE_MINUTES} min (limit {LIMIT} min)")

        output, items = run_pass(decisions, log)
        print("--- pass one: the job is alive, the log is stale")
        print(output.strip() or "(no output)")
        print(f"factory-watchdog items: {len([i for i in items if i['id'] == 'factory-watchdog'])}")
        if live is None or not live.get("loaded"):
            print("FAIL the gatekeep job is not loaded on this machine, "
                  "so pass one proves nothing")
            return 1
        if "WATCHDOG" in output:
            print("FAIL the stale log raised an alarm while the job was alive")
            return 1
        if [i for i in items if i["id"] == "factory-watchdog"]:
            print("FAIL the stale log wrote the factory-watchdog item")
            return 1
        print("PASS no alarm and no factory-watchdog item for a stale log")

        def stopped(label):
            if label != GATEKEEP:
                return live
            return {"loaded": False}

        lane.launchd_state = stopped
        output, items = run_pass(decisions, log)
        print("--- pass two: the same stale log, the job stopped")
        print(output.strip() or "(no output)")
        alarms = [i for i in items if i["id"] == "factory-watchdog"]
        print(f"factory-watchdog items: {len(alarms)}")
        if "WATCHDOG" not in output:
            print("FAIL a stopped job raised no alarm")
            return 1
        if len(alarms) != 1:
            print("FAIL the alarm did not write exactly one factory-watchdog item")
            return 1
        if GATEKEEP not in alarms[0]["title"]:
            print("FAIL the alarm does not name the stopped job")
            return 1
        print(f"PASS the alarm names the stopped job: {alarms[0]['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
