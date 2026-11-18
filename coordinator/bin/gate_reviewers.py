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
# the reviewer is blocked instead of the head moving on alone.
BLOCK_MARKERS = (
    "no credits", "credit balance", "out of credits", "insufficient_quota",
    "insufficient quota", "quota", "usage limit", "spend limit", "rate limit",
    "too many requests", "429", "401", "403", "unauthorized", "forbidden",
    "authentication", "invalid api key",
)

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


def error_text(value):
    """The text of a failed run's error, or "" when the value names no failure."""
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    if "thread" in value:
        thread = value.get("thread") or {}
        runs = value.get("recentRuns") or []
        failure = next((run for run in runs
                        if run.get("runId") == thread.get("latestRunId")), thread)
        if failure.get("status") != "failed":
            return ""
    else:
        failure = value
    error = failure.get("error")
    if isinstance(error, dict):
        return " ".join(str(error.get(field) or "") for field in ("code", "message"))
    return error if isinstance(error, str) else ""


def blocking_until(value, now=None):
    """The time a blocking provider error lifts, or None for any other end.

    A provider that says when it comes back sets the end; any other blocking
    error holds the reviewer for BLOCK_SECONDS."""
    now = time.time() if now is None else now
    text = error_text(value).lower()
    if not text or not any(marker in text for marker in BLOCK_MARKERS):
        return None
    match = RESET.search(text)
    if match:
        seconds = float(match.group(1)) * UNITS[match.group(2).lower()]
        if seconds > 0:
            return now + seconds
    return now + BLOCK_SECONDS
