"""The gate reviewer chain, and the reviewers blocked for every head.

A gate that ends without a verdict moves down this chain once. A reviewer that
fails with a blocking provider error is blocked for every head until its
window ends, and a new gate starts on the next reviewer meanwhile. The block
is one small file beside the queue, replaced whole rather than edited in
place, and its two callers write it while they hold the queue lock."""
import json
import os
import re
import time

REVIEWER_CHAIN = (
    {"instanceId": "codex", "model": "gpt-6.2-astra"},
    {"instanceId": "claudeAgent", "model": "claude-opus-5-5"},
)

BLOCK_FILE = "reviewers-blocked.json"
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


def identity(selection):
    """The name of one reviewer: the provider and the model together."""
    return f"{selection['instanceId']}:{selection['model']}"


def path(directory=None):
    return os.path.join(directory or os.environ.get("COORDQ_DIR", DEFAULT_DIR), BLOCK_FILE)


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
    """The time one record's block ends, or None for a record that cannot be read."""
    until = record.get("until") if isinstance(record, dict) else None
    if isinstance(until, (int, float)) and not isinstance(until, bool):
        return float(until)
    return None


def blocked(now=None, directory=None):
    """The reviewers blocked now, as identity -> the time the block ends."""
    now = time.time() if now is None else now
    return {name: until for name, record in read(directory).items()
            if (until := until_of(record)) and until > now}


def release_expired(now=None, directory=None):
    """Drop the blocks that have ended, and name the reviewers they free."""
    now = time.time() if now is None else now
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

    Returns None for a failure that is not a blocking provider error, and for
    a reviewer already blocked later than this failure says, so a caller logs
    one line per block.
    """
    now = time.time() if now is None else now
    until = blocking_until(value, now)
    if until is None:
        return None
    name = identity(selection)
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


def blocking_until(value, now=None):
    """The time a blocking provider error lifts, or None for any other end.

    A provider that says when it comes back sets the end; any other blocking
    error holds the reviewer for BLOCK_SECONDS."""
    now = time.time() if now is None else now
    code, message = error_fields(value)
    if not provider_refusal(code, message):
        return None
    match = RESET.search(message)
    if match:
        seconds = float(match.group(1)) * UNITS[match.group(2).lower()]
        if seconds > 0:
            return now + seconds
    return now + BLOCK_SECONDS
