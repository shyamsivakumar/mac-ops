"""One shared provider block record.

A provider that fails for a blocking reason is recorded in one place, so
every caller asks one question: is this provider blocked now? The record of
one provider is

    {"reason": <text>, "since": <ISO UTC>, "until": <ISO UTC>, "by": <writer>}

`since` is the moment the run failed, never the moment the failure was read
and never the moment the run started: a run that began at 10:00 and failed
at 10:35 says nothing about 10:35 through its start. `until` is the reset
the provider named, or an hour after the failure when it named none.

The store is one file beside the queue, `providers-blocked.json`, replaced
whole rather than edited in place, and its read-modify-write is guarded by
its own lock: the queue and the lane driver write it from different
processes, and a bare read then write from either one drops the block the
other had just earned.
"""
import fcntl
import json
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python without zoneinfo
    ZoneInfo = None

BLOCK_FILE = "providers-blocked.json"
LOCK_FILE = "providers-blocked.lock"
BLOCK_SECONDS = 3600.0
DEFAULT_DIR = os.path.expanduser("~/Code/coordinator/queue")

# A provider that says when it comes back in relative words: "your plan
# resets in 30 minutes", "retry after 3600s".
RELATIVE = re.compile(
    r"(?:resets?|try again|retry|available|back)\s+(?:in|after)\s+"
    r"(\d+(?:\.\d+)?)\s*(seconds?|minutes?|hours?|secs?|mins?|hrs?|s)\b", re.IGNORECASE)
UNITS = {"second": 1.0, "seconds": 1.0, "sec": 1.0, "secs": 1.0, "s": 1.0,
         "minute": 60.0, "minutes": 60.0, "min": 60.0, "mins": 60.0,
         "hour": 3600.0, "hours": 3600.0, "hr": 3600.0, "hrs": 3600.0}

# An absolute reset: a date and a time of day, or a time of day alone.
DATETIME = re.compile(
    r"\b(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)(Z|[+-]\d{2}:?\d{2})?\b")
TIME_ONLY = re.compile(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b")
# The words that make a time a reset rather than any time in a message.
RESET_WORD = re.compile(r"reset|retry|available|till|until|back\s+off", re.IGNORECASE)
# The zone a message states for its reset: "UTC", "+08:00", "Asia/Shanghai".
OFFSET = re.compile(r"([+-])(\d{2}):?(\d{2})\b")
NAMED_ZONE = re.compile(r"\b([A-Za-z]+(?:/[A-Za-z_]+)+)\b")

# The moment a failed run failed: the time it completed, else the time its
# record was last updated. A start time never says when a run failed.
FAILED_AT_FIELDS = ("completedAt", "updatedAt")

# The provider's own refusal. The code is compared whole, so a code is
# evidence and a number inside a message is not: `worker 14031 exited` holds
# the digits of 403 and is no refusal.
BLOCK_MARKERS = (
    "no credits", "credit balance", "out of credits", "insufficient_quota",
    "insufficient quota", "exceeded your current quota", "usage limit",
    "spend limit", "rate limit", "too many requests", "invalid api key",
    "quota exhausted", "quota exceeded", "payment required",
)
BLOCK_CODES = frozenset((
    "401", "402", "403", "429", "insufficient_quota", "rate_limit_exceeded",
    "quota_exceeded", "usage_limit", "spend_limit", "invalid_api_key",
    "authentication_error", "permission_error", "unauthorized", "forbidden",
))
STATUS = re.compile(
    r"\b(?:http|status(?:\s+code)?)\s*[:=]?\s*(?:401|402|403|429)\b"
    r"|\b(?:401|402|403|429)\s+(?:unauthorized|forbidden|too many requests|payment required)\b",
    re.IGNORECASE)


def identity(selection):
    """The name of one provider: the instance and the last segment of the model.

    The model is compared on its last segment, so a provider-prefixed
    spelling ("zai/glm-5.3") blocks the same provider as the plain one."""
    if not isinstance(selection, dict):
        return ""
    instance = selection.get("instanceId")
    model = str(selection.get("model") or "").split("/")[-1]
    return f"{instance}:{model}" if instance and model else ""


def queue_dir():
    return os.environ.get("COORDQ_DIR", DEFAULT_DIR)


def path():
    return os.path.join(queue_dir(), BLOCK_FILE)


def lock_path():
    return os.path.join(queue_dir(), LOCK_FILE)


_holding = [0]


@contextmanager
def locked(blocking=True):
    """Hold the block file for one read-modify-write.

    A caller that already holds the lock in this process keeps it, so a
    writer called from inside a held lock does not wait on its own lock.
    With `blocking=False` the lock is yielded as False when another process
    holds it, and the caller waits."""
    if _holding[0]:
        _holding[0] += 1
        try:
            yield True
        finally:
            _holding[0] -= 1
        return
    os.makedirs(queue_dir(), exist_ok=True)
    handle = open(lock_path(), "w")
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            yield False
            return
        _holding[0] = 1
        try:
            yield True
        finally:
            _holding[0] = 0
    finally:
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
    """A moment as the ISO text the store writes."""
    return datetime.fromtimestamp(float(seconds), timezone.utc).isoformat()


def run_records(value):
    """The records that may say when the run failed, the run's record first."""
    if not isinstance(value, dict):
        return []
    thread = value.get("thread") if isinstance(value.get("thread"), dict) else {}
    runs = value.get("recentRuns") or []
    failure = next((run for run in runs
                    if run.get("runId") == thread.get("latestRunId")), None)
    return [record for record in (failure, thread, value) if isinstance(record, dict)]


def failed_at(value):
    """When the failed run a value names failed, or None when it does not say.

    A completion time is read before an update time, and the run's record
    is read before the thread's. A start time is never read: a run that
    began at 10:00 and failed at 10:40 says nothing about 10:40 through
    its start."""
    if not isinstance(value, dict):
        return None
    for field in FAILED_AT_FIELDS:
        for source in run_records(value):
            seconds = parse_time(source.get(field))
            if seconds is not None:
                return seconds
    return None


def failure_of(value):
    """The failed run a value names, or None when it names no failure.

    A thread snapshot names its latest run, and that run is the failure
    when it failed. A plain string is a failure itself."""
    if isinstance(value, str):
        return {"error": value}
    if not isinstance(value, dict):
        return None
    if "thread" in value:
        thread = value.get("thread") or {}
        runs = value.get("recentRuns") or []
        failure = next((run for run in runs
                        if run.get("runId") == thread.get("latestRunId")), thread)
        if failure.get("status") not in ("failed", "interrupted"):
            return None
        return failure
    if value.get("status") in ("failed", "interrupted"):
        return value
    return None


def error_of(value):
    """The provider's error code and message of a failed run, as text."""
    failure = failure_of(value)
    error = failure.get("error") if failure else None
    if isinstance(error, dict):
        return str(error.get("code") or ""), str(error.get("message") or "")
    return "", error if isinstance(error, str) else ""


def provider_refusal(code, message):
    """Whether a failed run's error is the provider refusing to run.

    A refusal names the provider's own error code, or an HTTP status in the
    message, or one of the provider's billing and limit phrases. A
    substring is no evidence: `worker 14031 exited` holds the digits of 403
    and a local `disk quota exceeded` holds the word quota, and neither
    says anything about the provider."""
    if code.strip().lower() in BLOCK_CODES:
        return True
    if STATUS.search(message):
        return True
    lowered = message.lower()
    return any(marker in lowered for marker in BLOCK_MARKERS)


def zone_of(text, start=0):
    """The zone a message states for its reset, or None when it states none.

    An offset wins over a bare "UTC": "UTC+08:00" is eight hours ahead of
    UTC, not UTC, and reading it as UTC would hold the provider eight hours
    past the reset it named."""
    window = text[start:start + 48]
    match = OFFSET.search(window)
    if match:
        hours, minutes = int(match.group(2)), int(match.group(3))
        offset = timedelta(hours=hours, minutes=minutes)
        return timezone(-offset if match.group(1) == "-" else offset)
    if re.search(r"\b(?:UTC|GMT)\b", window, re.IGNORECASE):
        return timezone.utc
    if ZoneInfo is not None:
        match = NAMED_ZONE.search(window)
        if match:
            try:
                return ZoneInfo(match.group(1))
            except Exception:
                return None
    return None


def _epoch(date_text, time_text, zone):
    try:
        moment = datetime.fromisoformat(f"{date_text}T{time_text}")
    except ValueError:
        return None
    return moment.replace(tzinfo=zone or timezone.utc).timestamp()


def _absolute(message, base):
    """The absolute reset a message names, or None when it names none."""
    for match in DATETIME.finditer(message):
        if not RESET_WORD.search(message[max(0, match.start() - 60):match.start()]):
            continue
        zone = None
        if match.group(3):
            zone = timezone.utc if match.group(3) == "Z" else zone_of(match.group(3), 0)
        zone = zone or zone_of(message, match.end())
        return _epoch(match.group(1), match.group(2), zone)
    for match in TIME_ONLY.finditer(message):
        if not RESET_WORD.search(message[max(0, match.start() - 60):match.start()]):
            continue
        zone = zone_of(message, match.end()) or timezone.utc
        when = datetime.fromtimestamp(base, timezone.utc).astimezone(zone)
        seconds = _epoch(when.date().isoformat(), match.group(1), zone)
        if seconds is not None and seconds < base:
            seconds += 24 * 3600
        return seconds
    return None


def reset_at(message, failed=None):
    """The epoch seconds of the reset a provider error names, or None.

    A relative reset is measured from the failure, not from the moment the
    failure is read: a run that failed at 10:35 and says "resets in 30
    minutes" comes back at 11:05, not at 11:05 plus however long the
    failure took to read. An absolute reset is taken as it is written, in
    the zone the message states."""
    if not isinstance(message, str) or not message.strip():
        return None
    base = time.time() if failed is None else float(failed)
    match = RELATIVE.search(message)
    if match:
        seconds = float(match.group(1)) * UNITS.get(match.group(2).lower(), 0.0)
        # A reset of zero is a reset: the provider says it is free now, and
        # a block that waited an hour would hold it past what it promised.
        if seconds >= 0:
            return base + seconds
    return _absolute(message, base)


def record_block(selection, reason, failed=None, now=None, by="provider_block"):
    """Block one provider and return the record written, or None.

    The block runs from the moment the run failed to the reset the provider
    named, or to an hour after the failure when it named none. A window
    that has already closed blocks nobody and is not written.

    A failure read late never shortens a block a newer failure earned: the
    record that is already there keeps its end, and the provider stays out
    of the routing until that end, not until the older reset."""
    name = identity(selection)
    if not name:
        return None
    now = time.time() if now is None else now
    since = now if failed is None else float(failed)
    until = reset_at(reason, since)
    if until is None:
        until = since + BLOCK_SECONDS
    if until <= now:
        return None
    record = {"reason": reason, "since": stamp(since), "until": stamp(until), "by": by}
    with locked():
        state = read()
        current = state.get(name)
        if current is not None:
            current_failed = failure_time_of(current)
            if current_failed is not None and current_failed > since:
                return current
            current_until = until_of(current)
            if current_until is not None and current_until > until:
                return current
        state[name] = record
        write(state)
    return record


def failure_time_of(record):
    """The moment the failure a record was written for failed, or None."""
    if not isinstance(record, dict):
        return None
    return parse_time(record.get("since"))


def block_run(selection, value, now=None, by="provider_block"):
    """Block the provider a failed run names, and return the record written.

    The block starts when the run failed, not when the failure was read,
    and ends at the reset the error names. A failure that is not the
    provider refusing writes nothing."""
    failure = failure_of(value)
    if not failure:
        return None
    code, message = error_of(value)
    if not provider_refusal(code, message):
        return None
    return record_block(selection, message, failed=failed_at(value), now=now, by=by)


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


def is_blocked(selection, now=None):
    """Whether the provider a selection names is blocked now."""
    name = identity(selection)
    if not name:
        return False
    return name in blocked_identities(now)


def blocked_identities(now=None):
    """The identities of the providers blocked now.

    A block whose reset has passed is not a block: the provider answered
    again, or the window it named is over."""
    now = time.time() if now is None else now
    held = set()
    for name, record in read().items():
        until = until_of(record)
        if until is None or until > now:
            held.add(name)
    return held
