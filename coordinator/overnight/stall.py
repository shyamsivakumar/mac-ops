"""Stall detection for the overnight shift.

An item that shows no new commit and no new receipt for three ticks is not
moving. The shift reports it as stalled and keeps working it: the ticket's
newer instruction keeps the no-parking policy from Refs #376, so a stall is
reported, never parked. When the whole board shows no progress for three
ticks, the shift logs the stall, sweeps the board again and alerts Shyam.
The shift keeps running until every item is done or parked.

The rule lives in this one place: `observe` decides one item and `board`
decides the board. Both are pure: they read a state mapping and return the
new state and the event, so the shift writes the records (the shift log, the
receipt and the alert) with its own writers and every record is redacted the
way the rest of the shift's records are.

The state is the shift's own record, under `run/stall-state.json`, so the
shift keeps one record of its progress and not a second list of its work:
the board is the list.
"""

import datetime as dt
import json
import os
from pathlib import Path

import alarms

# The cap the spec names: three ticks with no new commit and no new receipt.
STALL_CAP = 3
# The alert the coordinator's board shows Shyam.
ALERT_ID = "factory-overnight-stall"
# The coordinator's board file. The driver writes its own alerts here, and
# the environment moves it for a fixture run.
BOARD_FILE = os.environ.get(
    "OVERNIGHT_BOARD", str(Path.home() / "Code" / "coordinator" / "decisions.json")
)


def new_state():
    """Return an empty stall state."""
    return {"items": {}, "board_idle": 0}


def state_path(root):
    """Return the path of the file that holds the stall state.

    The state lives with the shift's other records, under `run/`, so the
    shift keeps one record of its progress and not a second list."""
    return Path(root) / "run" / "stall-state.json"


def marker(head, receipt):
    """Return the marker of one item: its commit and its receipt.

    The marker changes when the item's pull request gets a new commit or
    the item gets a new dispatch receipt. Either one is progress."""
    return f"{head or ''}|{receipt or ''}"


def moved(state, key, item_marker):
    """Return True when the item's marker changed since the last tick.

    A tick that shows no change is an idle tick. The first tick of an item
    is idle too: there is nothing yet to compare it with."""
    entry = (state.get("items") or {}).get(key)
    if not isinstance(entry, dict):
        return False
    previous = entry.get("marker")
    return previous is not None and previous != item_marker


def pending(state, key, item_marker, cap=STALL_CAP):
    """Return True when this tick could report the item as stalled.

    The caller reads the board again before it decides, because the board
    the shift holds is cached and a stale head is not evidence that the
    item stopped moving."""
    entry = (state.get("items") or {}).get(key)
    if not isinstance(entry, dict):
        return False
    previous = entry.get("marker")
    if previous is None or previous != item_marker:
        return False
    return int(entry.get("idle") or 0) + 1 >= cap


def board_pending(state, cap=STALL_CAP):
    """Return True when this tick could stall the board."""
    return int(state.get("board_idle") or 0) + 1 >= cap


def observe(state, key, item_marker, cap=STALL_CAP):
    """Record one tick of one item and return the stall event, or None.

    A marker that changed is progress: the idle count starts again. A
    marker that did not change is one more idle tick. The idle count stops
    at the cap, so the tracking is bounded. When the idle count reaches the
    cap the item is reported as stalled, and the event says so.

    A stalled item is reported, not parked: the shift keeps working it."""
    items = state.setdefault("items", {})
    entry = items.get(key)
    entry = dict(entry) if isinstance(entry, dict) else {}
    previous = entry.get("marker")
    if previous is None:
        entry = {"marker": item_marker, "idle": 1, "stalled": False}
    elif item_marker != previous:
        entry = {"marker": item_marker, "idle": 0, "stalled": False}
    else:
        entry["idle"] = min(int(entry.get("idle") or 0) + 1, cap)
    items[key] = entry
    if entry["idle"] >= cap and not entry.get("stalled"):
        entry["stalled"] = True
        items[key] = entry
        return {"kind": "item", "item": key, "idle": entry["idle"], "cap": cap}
    return None


def prune(state, keys):
    """Return the state with the items that left the board dropped.

    The tracking is bounded by the board: an item that is not on the board
    is not tracked any more."""
    items = state.get("items")
    if not isinstance(items, dict):
        return state
    state["items"] = {key: entry for key, entry in items.items() if key in keys}
    return state


def arrived(state, keys):
    """Record the board's items and return the ones that just arrived.

    New work on the board is progress: the board moved, whatever the new
    item is and whether the shift has measured it. The tracking is bounded
    by the board: an item that left the board is dropped."""
    seen = state.get("board")
    if not isinstance(seen, dict):
        seen = {}
    fresh = {key for key in keys if key not in seen}
    state["board"] = {key: True for key in keys}
    return fresh


def board(state, progressed, items=0, cap=STALL_CAP):
    """Record one tick of the board and return the board stall event, or
    None.

    The board moved when any item moved or when new work arrived on it. A
    board with no item in it is not a stalled board: it is a board whose
    work is done.

    The board's first tick is its baseline: there is nothing yet to compare
    it with, so it counts as an idle tick, the way the first tick of an
    item does.

    The board is alerted once per episode, and the episode ends when the
    board moves again. The flag is not set here: the rule does not know
    whether the alert reached Shyam, so it keeps asking until the writer
    says the alert was delivered (`delivered`). The idle count stops at
    the cap, so the tracking is bounded."""
    if not items:
        state["board_idle"] = 0
        state.pop("board_alerted", None)
        return None
    if not state.get("board_seen"):
        state["board_seen"] = True
        progressed = False
    if progressed:
        state["board_idle"] = 0
        state.pop("board_alerted", None)
        return None
    idle = min(int(state.get("board_idle") or 0) + 1, cap)
    state["board_idle"] = idle
    if idle >= cap and not state.get("board_alerted"):
        return {"kind": "board", "idle": idle, "cap": cap}
    return None


def delivered(state):
    """Record that the board alert reached Shyam.

    The flag is set after the alert was written, so a board whose alert
    could not be written asks again on the next tick instead of going
    quiet for good."""
    state["board_alerted"] = True
    return state


def continues(state, cap=STALL_CAP):
    """Return True when the board stall is still on.

    The board is alerted once per episode and the flag says the alert was
    delivered, so the rule stops asking. The shift keeps asking anyway:
    the writer knows whether the alarm is due, it is quiet while the mute
    runs, and it comes back when the four hours are over. Without this
    the alarm could never come back during a stall that does not end."""
    if not isinstance(state, dict):
        return False
    if not state.get("board_alerted"):
        return False
    return int(state.get("board_idle") or 0) >= cap


def alarm_cause(reason, state):
    """Return the cause of the board stall: the reason and the stalled repos.

    The board stall is one alarm, and its cause names what is stuck: the
    items the shift reported as stalled. Two stalls on different repos are
    different causes, and a stall on the same repos is the same cause, so
    the second one stays quiet after the first one was answered."""
    items = state.get("items") if isinstance(state, dict) else None
    stalled = sorted(
        key for key, entry in (items or {}).items()
        if isinstance(entry, dict) and entry.get("stalled")
    )
    return reason + " | stalled: " + (", ".join(stalled) if stalled else "none")


def alert(reason, cause=None, path=None):
    """Write the alert that tells Shyam the board stopped moving.

    The alert is one item on the coordinator's board, the same board the
    merge alert and the watchdog use. The item is replaced, so one stalled
    board shows one alert and not one per tick.

    An alert that was acknowledged stays quiet for four hours: the board
    holds no item for it and the shift logs one line per tick. A
    different cause is a different alert and is written at once.

    Return the path it wrote and what it did: "wrote", "quiet" or
    "failed"."""
    target = Path(path or BOARD_FILE)

    def publish(action):
        """Read the board, change it, and write it, under the board lock.

        The board lock is taken first; when it cannot be taken the write
        falls back to a compare-and-swap, so the alarm is still published
        and two publishers still cannot erase one another's alarm."""
        item = None
        if action in ("raise", "unchecked"):
            item = {
                "id": ALERT_ID,
                "group": "Coordinator",
                "kind": "action",
                "title": "Overnight shift stalled: no board progress for 3 ticks",
                "cause": alarms.cause_of(cause or reason),
                "why": reason,
            }
        if alarms.route_update(target, ALERT_ID,
                               "raise" if item else "remove", item) != "wrote":
            return "failed"
        if action == "unchecked":
            # The key could not be written, so the answer to this alarm
            # cannot be recorded. The alarm is published anyway: a
            # storage failure must not hide a real failure from Shyam.
            print("stall: the alarm key could not be written; the answer to this alarm cannot be recorded")
        return None

    # The decision and the publication happen under the state lock, so an
    # answer that lands between them cannot be missed, and the board is
    # read, changed and written while another writer cannot read it
    # stale.
    action = alarms.decide_and_publish(ALERT_ID, cause or reason, publish)
    if action == "quiet":
        return "", "quiet"
    if action == "failed":
        return "", "failed"
    return str(target), "wrote"
