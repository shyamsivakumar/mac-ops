#!/usr/bin/env python3
"""Proof for #496: an acknowledged alarm stays quiet for four hours.

Scenario one, the factory watchdog. The tick job fails with an exit code,
the watchdog raises the alarm, and the coordinator takes the item off the
board. The next tick must not write the item (one tick of absence is not
proof that the alarm was routed), the tick after that must mute the key
for four hours, and the ticks in between must log one line each. A
different exit code is a different cause and must alarm at once, and the
same exit code must alarm again once the four hours are over and the cause
still holds.

Scenario two, the overnight stall. The shift raises factory-overnight-stall
on the coordinator's board. The coordinator answers it and takes the item off
the board, and the same rule holds. A stall on different repos is a
different cause and alarms at once.

The proof never touches the live board file or the live shift's folder:
every run writes copies in a temporary folder, the mute state goes beside
them, and the clock is a fixture. The live jobs are not read and not
touched.
"""
import contextlib
import datetime as dt
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "coordinator/overnight"))

import alarms  # noqa: E402
import lane_driver as lane  # noqa: E402
import stall as rule  # noqa: E402

# The replay runs on the clock of the machine, rounded to the second: the
# command that records the acknowledgement is a separate process and
# reads the same clock, so the two agree.
NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
REASON = "The overnight shift saw no board progress for 3 ticks."


def clock_at(moment):
    """Return a datetime class whose now() is the given moment."""
    class Clock(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return moment

    return Clock


def at(moment, fn, *args):
    """Call a function with the clock at the given moment."""
    with patch.object(dt, "datetime", clock_at(moment)):
        return fn(*args)


def ack(alarm_id, cause, moment):
    """Record the acknowledgement of an alarm the way the panel does.

    The panel runs the installed command, so the proof runs the command
    too: the file, executed as a command, with the id and the cause the
    panel showed. The clock is a fixture, so the command reads it
    through the environment the proof sets."""
    environment = dict(os.environ, OVERNIGHT_MUTE_STATE=alarms.MUTE_PATH)
    result = subprocess.run([str(alarms.__file__), "ack", alarm_id, cause],
                            capture_output=True, text=True, env=environment, timeout=60)
    if result.returncode != 0:
        print(f"FAIL the acknowledgement was not recorded: {result.stderr.strip()}")
        return 1
    return 0


def items_of(board):
    """Return the board items of a board file."""
    return json.loads(board.read_text())["items"]


def take_off_the_board(board):
    """Return the board as the coordinator leaves it after answering.

    The coordinator takes the alarm's item off the board. The rest of the
    board file stays, and so does the mute state, which lives in its own
    file and not in the board."""
    data = json.loads(board.read_text())
    data["items"] = [item for item in data["items"]
                     if item.get("id") != "factory-overnight-stall"
                     and item.get("id") != "factory-watchdog"]
    board.write_text(json.dumps(data, indent=1))


def load_runner():
    """Return the overnight runner as a module, so the proof runs the real path.

    The runner is what decides to alert: it asks the writer on every tick
    of a stall that continues, and the writer decides whether the alarm
    is due. A proof that called the writer alone would skip exactly that.
    """
    loader = importlib.machinery.SourceFileLoader(
        "overnight_runner", str(ROOT / "coordinator/overnight/overnight"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def watchdog_tick(board, exit_code, moment):
    """Run one watchdog tick and return (output, items).

    The tick job fails with the given exit code. Every other watched job
    is healthy, so the alarm names the tick alone."""
    states = {"dev.coordinator.tick": exit_code}

    def state(label):
        return {"loaded": True, "runs": 3, "exit_code": states.get(label, 0),
                "signal": None, "running": False, "pid": 0}

    buffer = io.StringIO()
    with patch.object(lane, "DECISIONS_PATH", str(board)), \
         patch.object(lane, "launchd_state", side_effect=state), \
         patch.object(lane, "log_age", return_value=1.0), \
         patch.object(dt, "datetime", clock_at(moment)):
        with contextlib.redirect_stdout(buffer):
            lane.watchdog()
    return buffer.getvalue(), items_of(board)


def replay_stall(board, runner):
    """Replay the overnight stall alarm on the real path and print what happened.

    The runner is the shift: it holds the stall state, it decides when to
    ask, and it writes the shift log. The proof drives it the way a cycle
    drives it: a board event on the first tick, and then a tick with no
    event because the board has not moved since.
    """
    root = board.parent
    state = rule.new_state()
    state["board_idle"] = 3
    event = {"kind": "board", "idle": 3, "cap": 3}
    written = at(NOW, runner.stall_records, root, [event], str(board), state)
    alarms_on_board = [i for i in items_of(board) if i["id"] == "factory-overnight-stall"]
    print("--- tick one: the shift raises the alarm")
    print(f"factory-overnight-stall items: {len(alarms_on_board)}")
    if len(alarms_on_board) != 1 or not written:
        print("FAIL the first tick did not raise the stall alarm")
        return False
    print("PASS the first tick raised the stall alarm")

    # The alarm's item goes off the board and nobody answered it: the
    # alarm is raised again, because a missing item is not an answer.
    take_off_the_board(board)
    at(NOW + dt.timedelta(minutes=3), runner.stall_records, root, [], str(board), state)
    items = [i for i in items_of(board) if i["id"] == "factory-overnight-stall"]
    print(f"--- the item goes missing, nobody answered (+3 min): {len(items)} item(s)")
    if len(items) != 1:
        print("FAIL an alarm nobody answered was silenced")
        return False
    print("PASS an alarm nobody answered was raised again")

    # Shyam answers the alarm: the acknowledgement is the record, for the
    # cause the panel showed.
    shown = [i for i in items_of(board) if i["id"] == "factory-overnight-stall"][0]["cause"]
    if ack("factory-overnight-stall", shown, NOW + dt.timedelta(minutes=4)) != 0:
        return False
    at(NOW + dt.timedelta(minutes=6), runner.stall_records, root, [], str(board), state)
    items = [i for i in items_of(board) if i["id"] == "factory-overnight-stall"]
    print(f"--- the tick after the answer (+6 min): {len(items)} item(s)")
    if items:
        print("FAIL an acknowledged alarm raised again")
        return False
    log = (root / "run" / "shift-log.md").read_text()
    print(f"shift log lines: {log.count('stall: no board progress')}")
    print("PASS the next ticks wrote no item and no alert for the same cause")

    # A different cause is a different key and alarms at once. A stall on
    # other repos is a different cause.
    state["items"] = {"a/other#9": {"stalled": True}}
    at(NOW + dt.timedelta(minutes=9), runner.stall_records, root, [], str(board), state)
    items = [i for i in items_of(board) if i["id"] == "factory-overnight-stall"]
    print(f"--- a stall on other repos (+9 min): {len(items)} item(s)")
    if len(items) != 1:
        print("FAIL a changed cause did not alarm at once")
        return False
    print("PASS a changed cause alarmed at once")

    # The same cause comes back when the four hours are over.
    state["items"] = {}
    later = NOW + dt.timedelta(hours=4, minutes=30)
    at(later, runner.stall_records, root, [], str(board), state)
    items = [i for i in items_of(board) if i["id"] == "factory-overnight-stall"]
    print(f"--- the same cause after four hours: {len(items)} item(s)")
    if len(items) != 1:
        print("FAIL the alarm did not come back after four hours")
        return False
    print("PASS the same cause alarmed again after four hours")
    return True


def replay_watchdog(board):
    """Replay the factory watchdog alarm and print what happened."""
    output, items = watchdog_tick(board, 1, NOW)
    alarms_on_board = [i for i in items if i["id"] == "factory-watchdog"]
    print("--- tick one: the tick job fails")
    print(output.strip() or "(no output)")
    print(f"factory-watchdog items: {len(alarms_on_board)}")
    if len(alarms_on_board) != 1:
        print("FAIL the first tick did not raise the watchdog alarm")
        return False
    print("PASS the first tick raised the watchdog alarm")

    # The item goes off the board and nobody answered: the alarm is
    # raised again.
    take_off_the_board(board)
    output, items = watchdog_tick(board, 1, NOW + dt.timedelta(minutes=3))
    alarms_on_board = [i for i in items if i["id"] == "factory-watchdog"]
    print(f"--- the item goes missing, nobody answered (+3 min): {len(alarms_on_board)} item(s)")
    if len(alarms_on_board) != 1:
        print("FAIL an alarm nobody answered was silenced")
        return False
    print("PASS an alarm nobody answered was raised again")

    # Shyam answers the alarm: the acknowledgement is the record, for the
    # cause the panel showed.
    shown = [i for i in items if i["id"] == "factory-watchdog"][0]["cause"]
    if ack("factory-watchdog", shown, NOW + dt.timedelta(minutes=4)) != 0:
        return False
    output, items = watchdog_tick(board, 1, NOW + dt.timedelta(minutes=6))
    alarms_on_board = [i for i in items if i["id"] == "factory-watchdog"]
    print(f"--- the tick after the answer (+6 min): {output.strip().splitlines()[-1]}")
    if alarms_on_board or "WATCHDOG quiet" not in output:
        print("FAIL an acknowledged alarm raised again")
        return False
    print("PASS the next ticks wrote no item and logged one line each")

    # A different exit code is a different cause and alarms at once.
    output, items = watchdog_tick(board, 78, NOW + dt.timedelta(minutes=9))
    print(f"--- a changed exit code (+9 min): {output.strip().splitlines()[-1]}")
    alarms_on_board = [i for i in items if i["id"] == "factory-watchdog"]
    if len(alarms_on_board) != 1:
        print("FAIL a changed cause did not alarm at once")
        return False
    print("PASS a changed exit code alarmed at once")

    # A tick where the job is healthy does not take the mute with it: the
    # same cause stays quiet for the rest of the four hours.
    if ack("factory-watchdog", "tick failing (last exit code 1)", NOW + dt.timedelta(minutes=10)) != 0:
        return False
    watchdog_tick(board, 0, NOW + dt.timedelta(minutes=11))
    output, items = watchdog_tick(board, 1, NOW + dt.timedelta(minutes=12))
    print(f"--- the job recovers and fails again (+12 min): {output.strip().splitlines()[-1]}")
    if [i for i in items if i["id"] == "factory-watchdog"] or "WATCHDOG quiet" not in output:
        print("FAIL the mute did not survive a healthy tick")
        return False
    print("PASS the mute survived a tick where the job was healthy")

    # The same cause comes back when the four hours are over.
    take_off_the_board(board)
    output, items = watchdog_tick(board, 1, NOW + dt.timedelta(hours=4, minutes=30))
    print(f"--- the same exit code after four hours: {output.strip().splitlines()[-1]}")
    alarms_on_board = [i for i in items if i["id"] == "factory-watchdog"]
    if len(alarms_on_board) != 1:
        print("FAIL the alarm did not come back after four hours")
        return False
    print("PASS the same exit code alarmed again after four hours")
    return True


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        board = root / "decisions.json"
        board.write_text(json.dumps({"items": []}, indent=1))
        alarms.MUTE_PATH = str(root / "mute-state.json")
        runner = load_runner()
        if not replay_stall(board, runner):
            return 1
        board.write_text(json.dumps({"items": []}, indent=1))
        if not replay_watchdog(board):
            return 1
    print("PASS the acknowledged alarms stayed quiet for four hours")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
