"""The provider health store, shared by the gate reviewers and the builders.

One file holds the providers that failed for a blocking reason, so a
reviewer and a builder never need two mechanisms (MO-1063 for reviewers,
MO-1082 for builders). A provider that runs out - a usage limit, no
credits, an auth failure - is blocked for every new launch and every send,
and is probed once an hour, or at the reset time the error names, until it
answers again.

The record of one provider:

    {"at": <epoch>, "reason": <text>, "probeAt": <epoch>,
     "resetAt": <epoch or null>, "probeRequestId": <id or null>, ...}

Every block and every unblock is logged once: the store returns the log
line and the caller prints it.
"""

import fcntl
import json
import os
import re
import time
from datetime import datetime, timezone

# One tiny probe per blocked provider, at most once an hour.
PROBE_INTERVAL = 3600

# The provider reasons that block a provider for every launch. The codes
# are the ones the two exhausted builders answered on 2026-11-17: GLM's
# 5-hour limit (429 code 1308) and MiniMax's Token Plan limit (429 code
# 2056).
BLOCK_MARKERS = (
    "usage limit", "usage_limit", "token plan",
    "5-hour limit", "5 hour limit", "no credits", "credit balance",
    "insufficient_quota", "insufficient quota", "quota exhausted",
    "quota exceeded", "exceeded your current quota", "spend limit",
    "rate limit", "rate_limit", "too many requests", "payment required",
    "unauthorized", "invalid api key", "authentication", "not authenticated",
    "forbidden",
)
BLOCK_CODES = ("401", "402", "429")


def queue_dir():
    return os.environ.get("COORDQ_DIR", os.path.expanduser("~/Code/coordinator/queue"))


def blocked_path():
    return os.path.join(queue_dir(), "providers-blocked.json")


def blocked_lock_path():
    return os.path.join(queue_dir(), "providers-blocked.lock")


class BlockedLock:
    """The lock on the blocked state.

    The lane driver, the queue and the ticket tool all write it, so the
    read-modify-write of one block cannot overwrite the block of another."""

    def __enter__(self):
        os.makedirs(queue_dir(), exist_ok=True)
        self.f = open(blocked_lock_path(), "w")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()
        return False


def identity(selection):
    """The identity of a provider selection.

    The model is compared on its last segment, so a provider-prefixed
    spelling ("zai/glm-5.3") blocks the same provider as the plain one."""
    if not isinstance(selection, dict):
        return ""
    instance = selection.get("instanceId")
    model = str(selection.get("model") or "").split("/")[-1]
    if not instance or not model:
        return ""
    return f"{instance}:{model}"


def load():
    """The blocked providers and their records."""
    try:
        with open(blocked_path()) as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    blocked = data.get("blocked") if isinstance(data, dict) else None
    if not isinstance(blocked, dict):
        raise ValueError("Invalid provider health store: expected blocked records")
    return blocked


def save(state):
    path = blocked_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump({"blocked": state}, f)
    os.replace(tmp, path)


def blocked_identities():
    """The identities of the blocked providers."""
    return set(load())


def blocked(selection):
    return identity(selection) in load()


def record(selection):
    return load().get(identity(selection))


def next_probe_at(now, reset_at=None):
    """When a blocked provider may be probed next.

    A provider that names a reset time is probed at that time and not
    before it. A block that names no reset is probed an hour later."""
    now = time.time() if now is None else now
    if reset_at:
        reset_at = float(reset_at)
        if reset_at > now:
            return reset_at
    return now + PROBE_INTERVAL


def block(selection, reason, now=None, reset_at=None):
    """Block a provider for every launch.

    Returns the log line for the block, or None when it was already
    blocked: each block is logged once."""
    ident = identity(selection)
    if not ident:
        return None
    with BlockedLock():
        state = load()
        if ident in state:
            return None
        now = time.time() if now is None else now
        state[ident] = {"at": now, "reason": reason,
                        "probeAt": next_probe_at(now, reset_at), "resetAt": reset_at}
        save(state)
    return f"blocked provider {ident}: {reason}"


def unblock(selection, request_id=None):
    """Unblock a provider. Returns the log line, or None.

    A successful probe unblocks through its request id: when one is given
    the record must still name that probe, so a stale success cannot
    delete a block that a newer failure wrote after it."""
    ident = identity(selection)
    with BlockedLock():
        state = load()
        record_at = state.get(ident)
        if record_at is None:
            return None
        if request_id is not None and record_at.get("probeRequestId") != request_id:
            return None
        del state[ident]
        save(state)
    return f"unblocked provider {ident}"


def probe_due(selection, now=None):
    """Whether a blocked provider may be probed again."""
    record_at = record(selection)
    if not record_at:
        return False
    now = time.time() if now is None else now
    deadline = record_at.get("probeAt")
    if deadline is None:
        deadline = record_at.get("resetAt")
    return now >= float(deadline or 0)


def note_probe(selection, request_id, now=None):
    """Record the probe of a blocked provider, so the next one waits.

    The reset the provider named is consumed here: a failed probe must
    not re-arm the provider against the same expired reset."""
    ident = identity(selection)
    with BlockedLock():
        state = load()
        record_at = state.get(ident)
        if not record_at:
            return None
        record_at["probeAt"] = (time.time() if now is None else now) + PROBE_INTERVAL
        record_at["probeRequestId"] = request_id
        record_at["resetAt"] = None
        save(state)
    return record_at


def note_probe_failure(selection, text, now=None, request_id=None):
    """Record a probe that ended without an answer.

    The deadline is anchored to the failure: an hour after it, or the
    reset the provider names in the failure, whichever is later."""
    ident = identity(selection)
    with BlockedLock():
        state = load()
        record_at = state.get(ident)
        if not record_at:
            return None
        probe_request = record_at.get("probeRequestId")
        if request_id is not None and request_id != probe_request:
            return record_at
        now = time.time() if now is None else now
        reset_at = reset_time(text, now)
        record_at["probeAt"] = next_probe_at(now, reset_at)
        record_at["resetAt"] = reset_at
        record_at["probeFailedAt"] = now
        record_at.pop("probeRequestId", None)
        save(state)
    return record_at


def block_reason(text):
    """The blocking provider reason in a failure text, or None."""
    if not isinstance(text, str) or not text:
        return None
    low = text.lower()
    for code in ("1308", "2056"):
        if re.search(r'(?:["\']?code["\']?\s*[:=]?\s*["\']?)' + code + r'\b', low):
            return code
    for marker in BLOCK_MARKERS:
        if marker in low:
            return marker
    for code in BLOCK_CODES:
        if re.search(r'(?:["\']?(?:status|code|error_code)["\']?\s*[:=]?\s*["\']?|http\s+)' + re.escape(code) + r'\b', low):
            return f"provider error {code}"
    return None


def reset_time(text, now=None):
    """The epoch seconds of the reset a provider error names, or None."""
    if not isinstance(text, str) or not text:
        return None
    now = time.time() if now is None else now
    match = re.search(r"resets?\s+in\s+(\d+)\s*(minutes?|mins?|hours?|hrs?)", text, re.I)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        seconds = amount * 3600 if unit.startswith(("hour", "hr")) else amount * 60
        return now + seconds
    match = re.search(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:?\d{2})?", text)
    if match:
        stamp = match.group(0).replace(" ", "T")
        if stamp.endswith("Z"):
            stamp = stamp[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(stamp)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    return None
