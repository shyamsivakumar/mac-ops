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
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "coordinator/overnight"))

import alarms  # noqa: E402
import lane_driver as lane  # noqa: E402
import stall as rule  # noqa: E402

NOW = dt.datetime(2026, 11, 17, 9, 0, tzinfo=dt.timezone.utc)
REASON = "The overnight shift saw no board progress for 3 ticks."


def clock_at(moment):
    """Return a datetime class whose now() is the given moment."""
    class Clock(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return moment

    return Clock


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


def stall_tick(board, cause, moment):
    """Run one stall tick and return the action it took."""
    with patch.object(dt, "datetime", clock_at(moment)):
        target, action = rule.alert(REASON, cause, board)
    return action


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


def replay_stall(board, cause):
    """Replay the overnight stall alarm and print what happened."""
    action = stall_tick(board, cause, NOW)
    print(f"--- tick one: the shift raises the alarm ({action})")
    alarms_on_board = [i for i in items_of(board) if i["id"] == "factory-overnight-stall"]
    print(f"factory-overnight-stall items: {len(alarms_on_board)}")
    if action != "wrote" or len(alarms_on_board) != 1:
        print("FAIL the first tick did not raise the stall alarm")
        return False
    print("PASS the first tick raised the stall alarm")

    # The coordinator answers the alarm and takes its item off the board.
    take_off_the_board(board)
    action = stall_tick(board, cause, NOW + dt.timedelta(minutes=3))
    print(f"--- tick after the answer (+3 min): {action}")
    if action != "held" or [i for i in items_of(board) if i["id"] == "factory-overnight-stall"]:
        print("FAIL the tick after the answer raised again")
        return False
    action = stall_tick(board, cause, NOW + dt.timedelta(minutes=6))
    print(f"--- the tick after that (+6 min): {action}")
    if action != "quiet" or [i for i in items_of(board) if i["id"] == "factory-overnight-stall"]:
        print("FAIL an acknowledged alarm raised again")
        return False
    print("PASS the next ticks wrote no item and no alert for the same cause")

    # A different cause is a different key and alarms at once. A stall on
    # other repos is a different cause.
    other = rule.alarm_cause(REASON, {"items": {"a/other#9": {"stalled": True}}})
    action = stall_tick(board, other, NOW + dt.timedelta(minutes=9))
    print(f"--- a stall on other repos (+9 min): {action}")
    items = [i for i in items_of(board) if i["id"] == "factory-overnight-stall"]
    if action != "wrote" or len(items) != 1:
        print("FAIL a changed cause did not alarm at once")
        return False
    print("PASS a changed cause alarmed at once")

    # The same cause comes back when the four hours are over.
    take_off_the_board(board)
    action = stall_tick(board, cause, NOW + dt.timedelta(hours=4, minutes=20))
    print(f"--- the same cause after four hours: {action}")
    items = [i for i in items_of(board) if i["id"] == "factory-overnight-stall"]
    if action != "wrote" or len(items) != 1:
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

    # The coordinator takes the item off the board.
    take_off_the_board(board)
    output, items = watchdog_tick(board, 1, NOW + dt.timedelta(minutes=3))
    print(f"--- tick after the answer (+3 min): {output.strip().splitlines()[-1]}")
    if [i for i in items if i["id"] == "factory-watchdog"] or "WATCHDOG held" not in output:
        print("FAIL the tick after the answer raised again")
        return False
    output, items = watchdog_tick(board, 1, NOW + dt.timedelta(minutes=6))
    print(f"--- the tick after that (+6 min): {output.strip().splitlines()[-1]}")
    if [i for i in items if i["id"] == "factory-watchdog"] or "WATCHDOG quiet" not in output:
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

    # The same cause comes back when the four hours are over.
    take_off_the_board(board)
    output, items = watchdog_tick(board, 1, NOW + dt.timedelta(hours=4, minutes=20))
    print(f"--- the same exit code after four hours: {output.strip().splitlines()[-1]}")
    alarms_on_board = [i for i in items if i["id"] == "factory-watchdog"]
    if len(alarms_on_board) != 1:
        print("FAIL the alarm did not come back after four hours")
        return False
    print("PASS the same exit code alarmed again after four hours")

    # A tick where the job is healthy does not take the mute with it.
    take_off_the_board(board)
    output, items = watchdog_tick(board, 1, NOW + dt.timedelta(hours=4, minutes=23))
    output, items = watchdog_tick(board, 1, NOW + dt.timedelta(hours=4, minutes=26))
    print(f"--- the same exit code again (+4 h 26 min): {output.strip().splitlines()[-1]}")
    if [i for i in items if i["id"] == "factory-watchdog"] or "WATCHDOG quiet" not in output:
        print("FAIL the alarm was not muted after the coordinator routed it")
        return False
    # A tick where the job is healthy: the alarm is not true any more.
    output, items = watchdog_tick(board, 0, NOW + dt.timedelta(hours=4, minutes=29))
    print(f"--- the job recovers (+4 h 29 min): {output.strip().splitlines()[-1]}")
    # The job fails again with the same exit code.
    output, items = watchdog_tick(board, 1, NOW + dt.timedelta(hours=4, minutes=32))
    print(f"--- the same exit code again (+4 h 32 min): {output.strip().splitlines()[-1]}")
    if [i for i in items if i["id"] == "factory-watchdog"] or "WATCHDOG quiet" not in output:
        print("FAIL the mute did not survive a healthy tick")
        return False
    print("PASS the mute survived a tick where the job was healthy")
    return True


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        board = root / "decisions.json"
        board.write_text(json.dumps({"items": []}, indent=1))
        alarms.MUTE_PATH = str(root / "mute-state.json")
        cause = rule.alarm_cause(REASON, {"items": {"a/one#1": {"stalled": True}}})
        if not replay_stall(board, cause):
            return 1
        board.write_text(json.dumps({"items": []}, indent=1))
        if not replay_watchdog(board):
            return 1
    print("PASS the acknowledged alarms stayed quiet for four hours")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
