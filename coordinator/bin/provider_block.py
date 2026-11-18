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
from datetime import datetime, timezone

from provider_reset import reset_at

BLOCK_FILE = "providers-blocked.json"
LOCK_FILE = "providers-blocked.lock"
BLOCK_SECONDS = 3600.0
DEFAULT_DIR = os.path.expanduser("~/Code/coordinator/queue")


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
# A provider that answers with the status code on its own, as a launch
# error does: "429; resets at 14:00 UTC". The code stands alone at the
# front of the message and is followed by punctuation or by nothing, so a
# number inside a message, and a count that begins with one, are still no
# evidence.
LEADING_STATUS = re.compile(
    r"^\s*(?:http\s+|status(?:\s+code)?\s*[:=]?\s*)?(401|402|403|429)(?![0-9A-Za-z])"
    r"(?:\s*$|\s*[^\sA-Za-z])", re.IGNORECASE)
# A local error that reads like a provider refusal. A full disk says
# nothing about the provider, and `disk quota exceeded` holds the words of
# a quota refusal without being one.
LOCAL_ERROR = re.compile(
    r"disk quota|no space left|enospc|disk full|out of disk|"
    r"filesystem.{0,24}full|local storage", re.IGNORECASE)


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
    and a local `disk quota exceeded` holds the words of a quota refusal,
    and neither says anything about the provider. A code that stands alone
    at the front of the message is evidence, because that is how a launch
    error names the status it was refused with."""
    if code.strip().lower() in BLOCK_CODES:
        return True
    if LOCAL_ERROR.search(message):
        return False
    if STATUS.search(message):
        return True
    if LEADING_STATUS.match(message):
        return True
    lowered = message.lower()
    return any(marker in lowered for marker in BLOCK_MARKERS)



def record_block(selection, reason, failed=None, now=None, by="provider_block"):
    """Block one provider and return the record written, or None.

    The block runs from the moment the run failed to the reset the provider
    named, or to an hour after the failure when it named none. A window
    that has already closed blocks nobody and is not written.

    A failure read late never replaces a newer failure's record. A newer
    failure always replaces an older one, even when its reset is sooner,
    and even when its reset has already passed: the provider's latest word
    about when it comes back is the one to keep, so an 11:00 refusal that
    names noon replaces a 10:00 record that named 14:00, and a refusal that
    says "retry after 0s" frees a provider a older refusal had held until
    14:00. The newer expiry is written even when it has passed, so a late
    replay of the older refusal cannot bring the block back."""
    name = identity(selection)
    if not name:
        return None
    now = time.time() if now is None else now
    since = now if failed is None else float(failed)
    until = reset_at(reason, since)
    if until is None:
        until = since + BLOCK_SECONDS
    record = {"reason": reason, "since": stamp(since), "until": stamp(until), "by": by}
    with locked():
        state = read()
        current = state.get(name)
        if current is not None:
            current_failed = failure_time_of(current)
            if current_failed is not None and current_failed > since:
                current_until = until_of(current)
                if current_until is None or current_until > now:
                    return current
                return None
        state[name] = record
        write(state)
    return record if until > now else None


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
