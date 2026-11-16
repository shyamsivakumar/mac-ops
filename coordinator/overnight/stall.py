"""Stall detection for the overnight shift.

An item that shows no new commit and no new receipt for three ticks is not
moving. The shift parks it as `stall` and moves on to the next item. When
the whole board shows no progress for three ticks, the shift logs the stall,
sweeps the board again and alerts Shyam. The shift keeps running until every
item is done or parked.

The rule lives in this one place: `observe` decides one item and `board`
decides the board. Both are pure: they read a state mapping and return the
new state and the event, so the shift writes the records (the shift log, the
receipt and the alert) with its own writers and every record is redacted the
way the rest of the shift's records are.

The state is the lane ledger's own record (`_stall`), so the shift keeps no
second list of its work: the board is the list and the ledger holds only the
progress the shift measured.
"""

import datetime as dt
import json
import os
from pathlib import Path

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


def appeared(state, key):
    """Return True when the item was not on the board before.

    A new item on the board is work that arrived, so the board moved."""
    return key not in (state.get("items") or {})


def pending(state, key, item_marker, cap=STALL_CAP):
    """Return True when this tick could park the item.

    The caller reads the board again before it parks, because the board
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


def stalled(state, key):
    """Return True when the item is parked as a stall.

    A parked item is skipped: the shift moves on to the next one."""
    entry = (state.get("items") or {}).get(key)
    if not isinstance(entry, dict):
        return False
    return bool(entry.get("stalled"))


def board(state, progressed, items=0, cap=STALL_CAP):
    """Record one tick of the board and return the board stall event, or
    None.

    The board moved when any item moved or when new work arrived on it. A
    board with no item in it is not a stalled board: it is a board whose
    work is done.

    The board's first tick is its baseline: there is nothing yet to compare
    it with, so it counts as an idle tick, the way the first tick of an
    item does.

    The board is alerted once per episode: the alert is not repeated until
    the board moves again. The idle count stops at the cap, so the
    tracking is bounded."""
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
        state["board_alerted"] = True
        return {"kind": "board", "idle": idle, "cap": cap}
    return None


def alert(reason, path=None):
    """Write the alert that tells Shyam the board stopped moving.

    The alert is one item on the coordinator's board, the same board the
    merge alert and the watchdog use. The item is replaced, so one stalled
    board shows one alert and not one per tick."""
    target = Path(path or BOARD_FILE)
    try:
        with open(target) as handle:
            decisions = json.load(handle)
    except (OSError, ValueError):
        return ""
    if not isinstance(decisions, dict):
        return ""
    items = decisions.get("items")
    if not isinstance(items, list):
        return ""
    kept = [
        item
        for item in items
        if not (isinstance(item, dict) and item.get("id") == ALERT_ID)
    ]
    kept.append(
        {
            "id": ALERT_ID,
            "group": "Coordinator",
            "kind": "action",
            "title": "Overnight shift stalled: no board progress for 3 ticks",
            "why": reason,
        }
    )
    decisions["items"] = kept
    decisions["updated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with open(str(target) + ".tmp", "w") as handle:
            json.dump(decisions, handle, indent=1)
        os.replace(str(target) + ".tmp", str(target))
    except OSError:
        return ""
    return str(target)
