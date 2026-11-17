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

The mute state lives in the shift's own records, under
`run/mute-state.json` next to the stall state, and not in the board file:
the coordinator rewrites the board file, and a board file that is
rewritten must not take the mute with it.

Two things mute a key. An explicit acknowledgement is a record with the
time it was given and the time the mute ends; the `alarms ack <alarm-id>`
command writes it. A routed alarm is a key that was raised and whose
board item stayed gone: the coordinator took the item off the board, so
the key is muted from that moment. One tick of absence is not proof: the
board has more than one writer and one of them can lose the item for a
tick, so the alarm waits a tick before it believes it.

An alarm that is not true any more drops its "raised" mark, so the same
cause can alarm again the next time it is true, but an acknowledgement
that is still running keeps the key quiet.
"""

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

# How long a key stays quiet after it was answered or routed.
MUTE_SECONDS = 4 * 60 * 60
# The key of the mute state inside the state file.
STATE_KEY = "alarms"
# The minutes of a quiet log and the minutes of a stuck run change on
# every tick, so they are not part of the cause. The idle tick count of a
# stall is the same: a stall that is reported on the fourth tick is the
# same stall as the one reported on the third.
VOLATILE = re.compile(r"\d+ min \(limit \d+\)|running \d+ min")
# The idle tick count of a stall changes with the tick it is reported on.
VOLATILE_TICKS = re.compile(r"\d+ ticks")
# The shift's own records: the mute state lives beside the stall state.
MUTE_PATH = os.environ.get(
    "OVERNIGHT_MUTE_STATE",
    "/Users/shyamsivakumar/Code/coordinator/.overnight/run/mute-state.json",
)
# A tick that finds the alarm's item gone does not believe it at once.
ABSENT_TICKS = 2


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
    cause = VOLATILE.sub("<time>", str(text or "")).strip()
    return VOLATILE_TICKS.sub("<ticks>", cause)


def key_of(alarm_id, cause):
    """Return the key of one alarm: its id and its cause."""
    return f"{alarm_id}|{cause_of(cause)}"


def state_path():
    """Return the path of the file that holds the mute state."""
    return Path(MUTE_PATH)


def load_state():
    """Return the mute state the shift keeps.

    A state that cannot be read is an empty state: every alarm is
    measured again from this tick on."""
    try:
        text = state_path().read_text()
    except OSError:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    state = data.get(STATE_KEY) if isinstance(data, dict) else None
    return state if isinstance(state, dict) else {}


def save_state(state):
    """Write the mute state and return True when it went to the file.

    The write is atomic, so a tick that reads while the state is being
    written reads the old state or the new one, never half of one."""
    path = state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / f"{path.name}.tmp"
        temporary.write_text(json.dumps({STATE_KEY: state}, indent=1) + "\n")
        os.replace(temporary, path)
    except OSError:
        return False
    return True


def entry(state, key):
    """Return the record of one key, or an empty record."""
    value = state.get(key) if isinstance(state, dict) else None
    return value if isinstance(value, dict) else {}


def until(state, key):
    """Return the epoch second the key stays quiet until, or None."""
    return moment(entry(state, key).get("until"))


def muted(state, key, now=None):
    """Return True when the key is quiet right now."""
    stop = until(state, key)
    if stop is None:
        return False
    current = now or dt.datetime.now(dt.timezone.utc)
    return current.timestamp() < stop


def acknowledge(state, key, now=None):
    """Quiet one key for four hours and return the record it wrote.

    The acknowledgement is the answer: the key stays quiet until the four
    hours are over, and a different cause is a different key."""
    current = now or dt.datetime.now(dt.timezone.utc)
    record = dict(entry(state, key))
    record["acked"] = stamp(current)
    record["until"] = stamp(current + dt.timedelta(seconds=MUTE_SECONDS))
    state[key] = record
    return record


def raised(state, alarm_id, cause, now=None):
    """Record that the key is on the board and return the record it wrote.

    A raised key has no acknowledgement: the alarm is on the board and
    waits for an answer."""
    current = now or dt.datetime.now(dt.timezone.utc)
    key = key_of(alarm_id, cause)
    state[key] = {"cause": cause_of(cause), "raised": stamp(current), "absent": 0}
    return state[key]


def gone(state, alarm_id):
    """Mark every key of one alarm as not true any more.

    The key keeps its acknowledgement, so an alarm that was answered
    stays quiet for the rest of the four hours, but the "raised" mark
    goes, so the same cause can alarm again when it is true again."""
    prefix = f"{alarm_id}|"
    for key in list(state or {}):
        if not key.startswith(prefix):
            continue
        record = state[key]
        if not isinstance(record, dict):
            continue
        record.pop("raised", None)
        record["absent"] = 0


def decide(state, alarm_id, cause, present, now=None):
    """Return what the shift does with one alarm.

    "raise" writes the board item, "quiet" writes nothing and mutes the
    key for four hours, and "hold" writes nothing for this tick because
    the board item went missing and one tick is not proof that the
    coordinator routed it.

    The rule: a key that was answered or routed stays quiet for four
    hours. A key that was raised and whose board item stayed gone was
    routed. A key that was never raised, or whose cause changed, is
    raised at once.

    `present` says whether the board holds the alarm's item right now."""
    current = now or dt.datetime.now(dt.timezone.utc)
    key = key_of(alarm_id, cause)
    record = entry(state, key)
    if record.get("acked"):
        stop = moment(record.get("until"))
        if stop is not None and current.timestamp() < stop:
            return "quiet"
        # The four hours are over, so the alarm is raised again.
        return "raise"
    if record.get("raised") and not present:
        count = int(record.get("absent") or 0) + 1
        record["absent"] = count
        state[key] = record
        if count >= ABSENT_TICKS:
            acknowledge(state, key, current)
            return "quiet"
        # The item was on the board and is gone. The board has more than
        # one writer, and one of them can lose the item for a tick, so
        # the alarm waits a tick before it believes it was routed.
        return "hold"
    if present:
        record["absent"] = 0
        state[key] = record
    return "raise"


def main(argv):
    """Quiet one alarm and print what it did.

    `alarms ack <alarm-id>` records the acknowledgement of every cause of
    that alarm, so the coordinator can answer an alarm without taking its
    item off the board. The item stays on the board until the coordinator
    routes it."""
    if len(argv) != 2 or argv[0] != "ack":
        sys.stderr.write("usage: alarms ack <alarm-id>\n")
        return 2
    state = load_state()
    prefix = f"{argv[1]}|"
    keys = [key for key in state if key.startswith(prefix)]
    if not keys:
        sys.stderr.write(f"alarms: no raised key for {argv[1]}\n")
        return 1
    for key in keys:
        acknowledge(state, key)
    if not save_state(state):
        sys.stderr.write("alarms: the mute state could not be written\n")
        return 1
    print(f"alarms: {argv[1]} quiet for {MUTE_SECONDS // 3600} hours ({len(keys)} key(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
