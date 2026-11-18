"""The store one provider block record lives in.

The file is `providers-blocked.json` beside the queue, replaced whole rather
than edited in place, and its read-modify-write is guarded by its own lock:
the queue and the lane driver write it from different processes, and a bare
read then write from either one drops the block the other had just earned.
"""
import fcntl
import json
import math
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone

BLOCK_FILE = "providers-blocked.json"
LOCK_FILE = "providers-blocked.lock"
BLOCK_SECONDS = 3600.0
DEFAULT_DIR = os.path.expanduser("~/Code/coordinator/queue")

def queue_dir():
    return os.environ.get("COORDQ_DIR", DEFAULT_DIR)


def path():
    return os.path.join(queue_dir(), BLOCK_FILE)


def lock_path():
    return os.path.join(queue_dir(), LOCK_FILE)


@contextmanager
def locked():
    """Hold the block file for one read-modify-write."""
    os.makedirs(queue_dir(), exist_ok=True)
    handle = open(lock_path(), "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def read():
    """The block records as written, as identity -> record.

    A missing file holds no blocks. A file that is not the store this
    module writes raises, because a store nobody can read is a store
    nobody can trust."""
    try:
        with open(path()) as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        raise ValueError(f"{path()} cannot be read: {e}") from e
    blocked = data.get("blocked") if isinstance(data, dict) else None
    if not isinstance(blocked, dict):
        raise ValueError(f"{path()} must hold a blocked object")
    return blocked


def write(state):
    target = path()
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = f"{target}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump({"blocked": state}, f, indent=1, sort_keys=True)
    os.replace(tmp, target)


def parse_time(value):
    """A recorded time as epoch seconds, or None for a value that is no time."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def stamp(seconds):
    """A moment as the ISO text the store writes.

    The text keeps the whole precision of the moment, because the failure
    time is what orders one refusal against another: rounding it up would
    make a refusal that came a tenth of a millisecond later look older,
    and the newer word on when the provider comes back would be lost."""
    return datetime.fromtimestamp(float(seconds), timezone.utc).isoformat()


def stamp_expiry(seconds):
    """The end of a block as the ISO text the store writes.

    The text carries whole milliseconds, rounded up. The pi reader parses
    the expiry with Date.parse, which reads milliseconds only, so a
    sub-millisecond expiry would be read a fraction early there and held
    here: the provider would be free in pi and blocked in Python. Rounding
    up keeps the two readers on one instant and never frees the provider
    before the reset it was given."""
    millis = math.ceil(float(seconds) * 1000.0)
    moment = datetime.fromtimestamp(millis // 1000, timezone.utc)
    moment = moment.replace(microsecond=(millis % 1000) * 1000)
    if moment.microsecond == 0:
        return moment.isoformat()
    return moment.isoformat(timespec="milliseconds")


def failure_time_of(record):
    """The moment the failure a record was written for failed, or None."""
    if not isinstance(record, dict):
        return None
    return parse_time(record.get("since"))


def until_of(record):
    """The time one record's block ends, or None when it names no end.

    A record that names no end is blocked until it is taken away: a store
    written by hand, before this module existed, names no end, and a block
    nobody can read the end of is not a block that may be dropped."""
    if not isinstance(record, dict):
        return None
    if "until" not in record:
        return None
    return parse_time(record.get("until"))


