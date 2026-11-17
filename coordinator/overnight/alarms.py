#!/usr/bin/env python3
"""The mute for the alarms the shift raises on the coordinator's board.

An alarm is a board item with an id and a cause. The id names the alarm
and the cause says what is wrong: the failing exit code, the silent log,
the board that stopped moving. The two together are the alarm's key.

Once the alarm has been answered on the decisions board, or the
coordinator has routed it, the key stays quiet for four hours: the next
tick writes no board item for that key and raises no alert for it. A
different cause is a different key, and it alarms at once. A muted alarm
still logs one line per tick, so the shift's log says what it did not
raise.

The mute state lives in the board's own file, under "alarms", so the board
and the shift read one state and the shift keeps no second list.

Two things mute a key. An explicit acknowledgement is a record in that
map with an "acked" time and the "until" time the mute ends. A routed
alarm is a key that was raised and whose board item is gone: the
coordinator took the item off the board, so the key is muted from that
moment. An alarm that is not true any more drops its keys, so the same
cause can alarm again the next time it is true.
"""

import datetime as dt
import json
import os
import re
import sys

# How long a key stays quiet after it was answered or routed.
MUTE_SECONDS = 4 * 60 * 60
# The key of the mute state inside the board file.
STATE_KEY = "alarms"
# The minutes of a quiet log and the minutes of a stuck run change on
# every tick, so they are not part of the cause.
VOLATILE = re.compile(r"\d+ min \(limit \d+\)|running \d+ min")
# The board file, so the module can be used on its own.
BOARD_FILE = os.environ.get(
    "OVERNIGHT_BOARD", str(os.path.expanduser("~/Code/coordinator/decisions.json"))
)


def stamp(now=None):
    """Return the UTC stamp of a moment."""
    moment = now or dt.datetime.now(dt.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def moment(text):
    """Return the epoch second of a stamp, or None when it is not one."""
    if not isinstance(text, str) or not text:
        return None
    try:
        parsed = dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    return parsed.replace(tzinfo=dt.timezone.utc).timestamp()


def cause_of(text):
    """Return the cause of one alarm, without the parts that change.

    The minutes of a quiet log and the minutes of a stuck run change on
    every tick, so they are not part of the cause: the same quiet log is
    the same cause. The exit code and the signal are part of it: a job
    that fails with a new code is a new cause and alarms at once."""
    return VOLATILE.sub("<time>", str(text or "")).strip()


def key_of(alarm_id, cause):
    """Return the key of one alarm: its id and its cause."""
    return f"{alarm_id}|{cause_of(cause)}"


def read(decisions):
    """Return the mute state the board keeps."""
    state = decisions.get(STATE_KEY) if isinstance(decisions, dict) else None
    return state if isinstance(state, dict) else {}


def entry(decisions, key):
    """Return the record of one key, or an empty record."""
    value = read(decisions).get(key)
    return value if isinstance(value, dict) else {}


def until(decisions, key):
    """Return the epoch second the key stays quiet until, or None."""
    return moment(entry(decisions, key).get("until"))


def muted(decisions, key, now=None):
    """Return True when the key is quiet right now."""
    stop = until(decisions, key)
    if stop is None:
        return False
    current = now or dt.datetime.now(dt.timezone.utc)
    return current.timestamp() < stop


def acknowledge(decisions, key, now=None):
    """Quiet one key for four hours and return the record it wrote.

    The acknowledgement is the answer: the key stays quiet until the four
    hours are over, and a different cause is a different key."""
    current = now or dt.datetime.now(dt.timezone.utc)
    state = read(decisions)
    record = dict(entry(decisions, key))
    record["acked"] = stamp(current)
    record["until"] = stamp(current + dt.timedelta(seconds=MUTE_SECONDS))
    state[key] = record
    decisions[STATE_KEY] = state
    return record


def raised(decisions, alarm_id, cause, now=None):
    """Record that the key is on the board and return the record it wrote.

    A raised key has no acknowledgement: the alarm is on the board and
    waits for an answer."""
    current = now or dt.datetime.now(dt.timezone.utc)
    state = read(decisions)
    key = key_of(alarm_id, cause)
    record = {"cause": cause_of(cause), "raised": stamp(current)}
    state[key] = record
    decisions[STATE_KEY] = state
    return record


def forget(decisions, alarm_id):
    """Drop every key of one alarm and return the keys it dropped.

    An alarm that is not true any more is over, so its keys go and the
    same cause can alarm again the next time it is true."""
    state = read(decisions)
    prefix = f"{alarm_id}|"
    dropped = [key for key in state if key.startswith(prefix)]
    for key in dropped:
        del state[key]
    if dropped:
        decisions[STATE_KEY] = state
    return dropped


def decide(decisions, alarm_id, cause, present, now=None):
    """Return what the shift does with one alarm: "raise" or "quiet".

    The rule: a key that was answered or routed stays quiet for four
    hours. A key that was raised and whose board item is gone was routed,
    so it is muted from that moment. A key that was never raised, or whose
    cause changed, is raised at once.

    `present` says whether the board holds the alarm's item right now."""
    current = now or dt.datetime.now(dt.timezone.utc)
    key = key_of(alarm_id, cause)
    record = entry(decisions, key)
    if record.get("acked"):
        stop = moment(record.get("until"))
        if stop is not None and current.timestamp() < stop:
            return "quiet"
        # The four hours are over, so the alarm is raised again.
        return "raise"
    if record.get("raised") and not present:
        acknowledge(decisions, key, current)
        return "quiet"
    return "raise"


def board(path=None):
    """Return the board file as a mapping, or an empty one."""
    target = path or BOARD_FILE
    try:
        with open(target) as handle:
            decisions = json.load(handle)
    except (OSError, ValueError):
        return {}
    return decisions if isinstance(decisions, dict) else {}


def write(decisions, path=None):
    """Write the board file and return the path it went to."""
    target = path or BOARD_FILE
    with open(str(target) + ".tmp", "w") as handle:
        json.dump(decisions, handle, indent=1)
    os.replace(str(target) + ".tmp", str(target))
    return str(target)


def main(argv):
    """Quiet one alarm on the board and print what it did.

    `alarms ack <alarm-id>` records the acknowledgement of every cause of
    that alarm, so the coordinator can answer an alarm without taking its
    item off the board. The item stays on the board until the coordinator
    routes it."""
    if len(argv) != 2 or argv[0] != "ack":
        sys.stderr.write("usage: alarms ack <alarm-id>\n")
        return 2
    decisions = board()
    state = read(decisions)
    prefix = f"{argv[1]}|"
    keys = [key for key in state if key.startswith(prefix)]
    if not keys:
        sys.stderr.write(f"alarms: no raised key for {argv[1]}\n")
        return 1
    for key in keys:
        acknowledge(decisions, key)
    write(decisions)
    print(f"alarms: {argv[1]} quiet for {MUTE_SECONDS // 3600} hours ({len(keys)} key(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
