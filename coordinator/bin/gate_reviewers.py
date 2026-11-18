"""The gate reviewer chain, and the reviewers blocked for every head.

A gate that ends without a verdict moves down this chain once. A reviewer that
fails with a blocking provider error is blocked for every head until its
window ends, and a new gate starts on the next reviewer meanwhile. The block
is one small file beside the queue, replaced whole rather than edited in
place, and it guards its own read-modify-write: the gatekeeper writes it while
it holds the queue lock, and the dispatcher writes it while it holds no lock
at all, so the file is what serializes them.

The window runs from the moment the run failed, not from the moment this
process first reads the failure: a gate can fail at 10:00 and be read at
10:25, and a block measured from the read would hold the reviewer 25 minutes
past the reset the provider named."""
import fcntl
import json
import math
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone

REVIEWER_CHAIN = (
    {"instanceId": "codex", "model": "gpt-6.2-astra"},
    {"instanceId": "claudeAgent", "model": "claude-opus-5-5"},
)

BLOCK_FILE = "reviewers-blocked.json"
LOCK_FILE = "reviewers-blocked.lock"
BLOCK_SECONDS = 3600.0
DEFAULT_DIR = os.path.expanduser("~/Code/coordinator/queue")

# A run that fails for one of these reasons says nothing about the diff, so
# the reviewer is blocked instead of the head moving on alone. Every marker is
# a phrase only a provider's own refusal uses. A bare `quota` is not one: a
# local `disk quota exceeded` says nothing about the provider and would block a
# healthy reviewer for every head. A bare auth word is not one either, since a
# `fatal: Authentication failed` from a git push inside the reviewer is not the
# provider refusing; the provider names those as an error code or an HTTP
# status, which BLOCK_CODES and STATUS match.
BLOCK_MARKERS = (
    "no credits", "credit balance", "out of credits", "insufficient_quota",
    "insufficient quota", "exceeded your current quota", "usage limit",
    "spend limit", "rate limit", "too many requests", "invalid api key",
)
# The provider's own error codes. The code field is compared whole, so a code
# is evidence and a number inside a message is not.
BLOCK_CODES = frozenset((
    "401", "403", "429", "insufficient_quota", "rate_limit_exceeded",
    "quota_exceeded", "usage_limit", "spend_limit", "invalid_api_key",
    "authentication_error", "permission_error", "unauthorized", "forbidden",
))
# An HTTP status is evidence only when the message names it as one. Bare digits
# are not: `worker 14031 exited` holds the digits of 403 and is no refusal.
STATUS = re.compile(r"\b(?:http|status(?:\s+code)?)\s*[:=]?\s*(?:401|403|429)\b"
                    r"|\b(?:401|403|429)\s+(?:unauthorized|forbidden|too many requests)\b",
                    re.IGNORECASE)

# A provider that says when it comes back: "your plan resets in 20 minutes".
RESET = re.compile(r"(?:resets?|try again|retry|available|back)\s+(?:in|after)\s+"
                   r"(\d+(?:\.\d+)?)\s*(second|minute|hour)s?", re.IGNORECASE)
UNITS = {"second": 1.0, "minute": 60.0, "hour": 3600.0}

# The moment a failed run failed: the time it completed, else the time its
# record was last updated. A start time never says when a run failed.
FAILED_AT_FIELDS = ("completedAt", "updatedAt")


def identity(selection):
    """The name of one reviewer: the provider and the model together."""
    return f"{selection['instanceId']}:{selection['model']}"


def path(directory=None):
    return os.path.join(directory or os.environ.get("COORDQ_DIR", DEFAULT_DIR), BLOCK_FILE)


def lock_path(directory=None):
    return os.path.join(directory or os.environ.get("COORDQ_DIR", DEFAULT_DIR), LOCK_FILE)


@contextmanager
def locked(directory=None):
    """Hold the block file for one read-modify-write.

    The two writers hold different locks: the gatekeeper writes this file
    while it holds the queue lock and the dispatcher failure path writes it
    while it holds nothing. A bare read then write from either side replaces
    the whole file with a copy the other's block was not in, dropping a block
    a reviewer had just earned, or freeing one that had just been recorded.
    Readers need nothing: a write is one atomic replace."""
    handle = open(lock_path(directory), "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def read(directory=None):
    """The block records as written, as identity -> {until, at}."""
    try:
        with open(path(directory)) as f:
            records = json.load(f)
    except (OSError, ValueError):
        return {}
    return records if isinstance(records, dict) else {}


def write(records, directory=None):
    target = path(directory)
    with open(target + ".tmp", "w") as f:
        json.dump(records, f, indent=1, sort_keys=True)
    os.replace(target + ".tmp", target)


def until_of(record):
    """The time one record's block ends, or None for a record that cannot be read.

    A record whose end is not a finite time reads as no end at all, so it is
    released like an expired one instead of holding the reviewer forever: a
    JSON `NaN` compares false against every deadline and would never expire."""
    until = record.get("until") if isinstance(record, dict) else None
    if isinstance(until, (int, float)) and not isinstance(until, bool):
        return float(until) if math.isfinite(until) else None
    return None


def blocked(now=None, directory=None):
    """The reviewers blocked now, as identity -> the time the block ends."""
    now = time.time() if now is None else now
    return {name: until for name, record in read(directory).items()
            if (until := until_of(record)) and until > now}


def release_expired(now=None, directory=None):
    """Drop the blocks that have ended, and name the reviewers they free."""
    now = time.time() if now is None else now
    with locked(directory):
        records = read(directory)
        ended = sorted(name for name, record in records.items()
                       if (until_of(record) or 0) <= now)
        for name in ended:
            del records[name]
        if ended:
            write(records, directory)
    return ended


def block_reviewer(selection, value, now=None, directory=None):
    """Block the reviewer a failed gate run names, and return when it ends.

    Returns the end only when this failure starts the block, so a caller
    logs one line per block. A distinct failure of a reviewer that is
    already blocked extends its block to the later window it names, and a
    failure that names an earlier window leaves the block alone; both
    return None. A failure that is not a blocking provider error returns
    None and writes nothing.
    """
    now = time.time() if now is None else now
    until = blocking_until(value, now)
    if until is None:
        return None
    name = identity(selection)
    with locked(directory):
        records = read(directory)
        current = until_of(records.get(name))
        if current is not None and current > now:
            if until > current:
                records[name] = {"until": until, "at": now}
                write(records, directory)
            return None
        records[name] = {"until": until, "at": now}
        write(records, directory)
    return until


def is_blocked(selection, now=None, directory=None):
    return identity(selection) in blocked(now, directory)


def starting_reviewer(now=None, directory=None):
    """The reviewer a new gate starts on, or None when every one is blocked."""
    held = blocked(now, directory)
    return next((entry for entry in REVIEWER_CHAIN if identity(entry) not in held), None)


def failure_of(value):
    """The failed run a value names, or None when it names no failure."""
    if isinstance(value, str):
        return {"error": value}
    if not isinstance(value, dict):
        return None
    if "thread" in value:
        thread = value.get("thread") or {}
        runs = value.get("recentRuns") or []
        failure = next((run for run in runs
                        if run.get("runId") == thread.get("latestRunId")), thread)
        return failure if failure.get("status") == "failed" else None
    return value


def error_fields(value):
    """The provider's error code and message of a failed run, as text."""
    failure = failure_of(value)
    error = failure.get("error") if failure else None
    if isinstance(error, dict):
        return str(error.get("code") or ""), str(error.get("message") or "")
    return "", error if isinstance(error, str) else ""


def provider_refusal(code, message):
    """Whether a failed run's error is the provider refusing to run.

    A refusal names the provider's own error code, or an HTTP status in the
    message, or one of the provider's billing and limit phrases. A substring is
    no evidence: `worker 14031 exited` holds the digits of 403, and a local
    `disk quota exceeded` holds the word quota, and neither says anything about
    the provider."""
    if code.strip().lower() in BLOCK_CODES:
        return True
    if STATUS.search(message):
        return True
    lowered = message.lower()
    return any(marker in lowered for marker in BLOCK_MARKERS)


def parse_time(value):
    """A recorded time as epoch seconds, or None for a value that is no time."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def failed_at(value):
    """When the failed run a value names failed, or None when it does not say.

    A completion time is read before an update time, and the run's record
    before the thread's. A start time is never read: a run that began at 10:00
    and failed at 10:40 says nothing about 10:40 through its start."""
    if not isinstance(value, dict):
        return None
    thread = value.get("thread") if isinstance(value.get("thread"), dict) else {}
    for field in FAILED_AT_FIELDS:
        for source in (failure_of(value) or {}, thread):
            seconds = parse_time(source.get(field))
            if seconds is not None:
                return seconds
    return None


def blocking_until(value, now=None):
    """The time a blocking provider error lifts, or None for any other end.

    A provider that says when it comes back sets the end; any other blocking
    error holds the reviewer for BLOCK_SECONDS. Both windows start when the
    run failed, so a failure read long after it happened holds the reviewer
    for what is left of the window it named and not a minute more. A window
    that closed before this read has already ended, so it blocks nobody."""
    now = time.time() if now is None else now
    code, message = error_fields(value)
    if not provider_refusal(code, message):
        return None
    seconds = BLOCK_SECONDS
    match = RESET.search(message)
    if match:
        named = float(match.group(1)) * UNITS[match.group(2).lower()]
        if named > 0:
            seconds = named
    start = failed_at(value)
    until = (now if start is None else min(start, now)) + seconds
    return until if until > now else None
