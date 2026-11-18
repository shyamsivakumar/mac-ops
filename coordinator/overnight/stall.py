"""Stall detection for the overnight shift.

An item that shows no new commit and no new receipt for three ticks is not
moving. The shift reports it as stalled and keeps working it: the ticket's
newer instruction keeps the no-parking policy from Refs #376, so a stall is
reported, never parked. When the whole board shows no progress for three
ticks, the shift logs the stall, sweeps the board again and alerts Shyam.
The shift keeps running until every item is done or parked.

The board's progress is more than a moved item: a merged pull request, a
closed ticket and a ticket that changed stage are progress too. The work
landed, so the board moved, and a board that keeps landing work is not
stalled (Refs #520).

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

# The cap the spec names: three ticks with no new commit and no new receipt.
STALL_CAP = 3
# How many board progress events the shift remembers. The memory is
# bounded, so a long night cannot grow the state without limit.
PROGRESS_MEMORY = 200
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


def progress(state, events):
    """Return the board events the shift has not seen before.

    An event is one thing that happened on the board: a merged pull
    request, a closed ticket or a ticket that changed stage. Every event
    counts once. An event the shift has already seen is not progress
    again, or a board that merged one pull request would never stall."""
    seen = state.get("board_events")
    if not isinstance(seen, dict):
        seen = {}
    fresh = []
    for event in events or []:
        key = str(event)
        if key not in seen:
            seen[key] = True
            fresh.append(key)
    if len(seen) > PROGRESS_MEMORY:
        for key in list(seen)[:len(seen) - PROGRESS_MEMORY]:
            seen.pop(key, None)
    state["board_events"] = seen
    return fresh


def staged(state, stages):
    """Record the board's ticket stages and return True when one changed.

    A ticket that changed stage is progress: the board moved. A ticket
    that arrived is progress too, and `arrived` counts it. A ticket that
    left the board is not counted here: a closed ticket is progress, and
    the shift reads the closed tickets to know."""
    previous = state.get("board_stages")
    if not isinstance(previous, dict):
        previous = {}
    changed = any(key in previous and previous[key] != stage
                  for key, stage in (stages or {}).items())
    state["board_stages"] = dict(stages or {})
    return changed


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
