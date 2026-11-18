"""The gate reviewer chain, its positions and its blocked state.

One list of reviewers serves every gate. A gate that ends without a
verdict moves down the chain, one reviewer per head, and waits when the
chain is exhausted. A reviewer that fails for a blocking provider reason
(no credits, usage limit, auth) is blocked for every head: new gates
start on the next reviewer until it recovers (Shyam 2026-11-17 18:15 PT).
"""

import fcntl
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

# The chain, in order: the Codex subscription on gpt-6.2-astra first —
# the openai-api reviewer left the chain when its org ran out of credits
# (Refs #521, 2026-11-17 19:20 PT) — then the Claude Agent on Opus 5.5
# as the fallback. Reviews run on GPT-6.2 Astra first; Opus takes over
# only when Astra cannot run (Shyam 2026-11-17).
REVIEWER_CHAIN = (
    {"instanceId": "codex", "model": "gpt-6.2-astra"},
    {"instanceId": "claudeAgent", "model": "claude-opus-5-5"},
)

# One tiny probe per blocked reviewer, at most once an hour.
PROBE_INTERVAL = 3600

# The provider reasons that block a reviewer for every head. The text of
# a failure is often missing (the provider never answers), so the shape
# of the failure carries the same meaning: no executed model and no
# answer means the reviewer could not run at all.
BLOCK_MARKERS = (
    "no credits", "credit balance", "insufficient_quota", "insufficient quota",
    "exceeded your current quota", "quota exhausted", "quota exceeded",
    "usage limit", "spend limit", "rate limit", "too many requests",
    "payment required", "unauthorized", "invalid api key", "authentication",
    "not authenticated", "forbidden",
)
BLOCK_CODES = ("401", "402", "429")


def identity(selection):
    """The identity of a reviewer selection.

    A selection that names a chain member gets that member's identity, so
    a provider-prefixed spelling ("subscriptions/gpt-6.2-astra") blocks
    the same reviewer as the plain one."""
    if not isinstance(selection, dict):
        return ""
    instance = selection.get("instanceId")
    model = selection.get("model")
    if instance and model:
        for member in REVIEWER_CHAIN:
            if same_reviewer(member, instance, model):
                return f"{member['instanceId']}:{member['model']}"
    return f"{instance}:{model}"


def same_reviewer(selection, instance, model):
    """Whether an instance and model name the given chain member.

    The model spelling a thread reports can carry a provider prefix
    ("subscriptions/gpt-6.2-astra"), so the model is compared on its
    last segment."""
    if not isinstance(selection, dict):
        return False
    if selection.get("instanceId") != instance:
        return False
    want = str(selection.get("model") or "").split("/")[-1]
    got = str(model or "").split("/")[-1]
    return bool(want) and want == got


def chain_index(selection):
    """The chain position of a reviewer, or -1 when it is not in it."""
    if not isinstance(selection, dict):
        return -1
    for index, member in enumerate(REVIEWER_CHAIN):
        if identity(member) == identity(selection):
            return index
    for index, member in enumerate(REVIEWER_CHAIN):
        if same_reviewer(member, selection.get("instanceId"), selection.get("model")):
            return index
    return -1


def selection_for(name):
    """The chain member with that identity, or None."""
    for member in REVIEWER_CHAIN:
        if identity(member) == name:
            return member
    return None


def selection_for_model(model):
    """The chain member with that model name, or None.

    A model name on its own is enough for a gate title, which carries the
    model in brackets. The full name is matched first, so the OpenAI API
    spelling is not mistaken for the Codex subscription one."""
    if not model:
        return None
    for member in REVIEWER_CHAIN:
        if member["model"] == model:
            return member
    for member in REVIEWER_CHAIN:
        if "/" not in member["model"] and str(model).split("/")[-1] == member["model"]:
            return member
    return None


def next_reviewer(current, tried=(), blocked=()):
    """The next chain member after the current one.

    A member that was already tried for this head, or that is blocked for
    every head, is skipped. None means the chain is exhausted: the head
    waits."""
    index = chain_index(current)
    if index < 0:
        return None
    seen = set(tried or ())
    blocked = set(blocked or ())
    for member in REVIEWER_CHAIN[index + 1:]:
        if identity(member) in seen or identity(member) in blocked:
            continue
        return member
    return None


def reviewer_after(current, blocked=()):
    """The reviewer a head moves to after the one that ran.

    A head whose previous reviewer is unknown is taken to have run on the
    chain head, so it moves to the second reviewer. None means the chain
    is exhausted: the head waits."""
    index = chain_index(current)
    if index < 0:
        index = 0
    blocked = set(blocked or ())
    for member in REVIEWER_CHAIN[index + 1:]:
        if identity(member) in blocked:
            continue
        return member
    return None


def first_reviewer(blocked=()):
    """The first chain member that is not blocked."""
    blocked = set(blocked or ())
    for member in REVIEWER_CHAIN:
        if identity(member) not in blocked:
            return member
    return None


def queue_dir():
    return os.environ.get("COORDQ_DIR", os.path.expanduser("~/Code/coordinator/queue"))


def blocked_path():
    return os.path.join(queue_dir(), "reviewers-blocked.json")


def blocked_lock_path():
    return os.path.join(queue_dir(), "reviewers-blocked.lock")


class BlockedLock:
    """The lock on the blocked state.

    The lane driver and the queue both write it, so the read-modify-write
    of one block cannot overwrite the block of the other."""

    def __enter__(self):
        os.makedirs(queue_dir(), exist_ok=True)
        self.f = open(blocked_lock_path(), "w")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()
        return False


def load_blocked():
    """The blocked reviewers and their records."""
    try:
        with open(blocked_path()) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    blocked = data.get("blocked") if isinstance(data, dict) else None
    return blocked if isinstance(blocked, dict) else {}


def save_blocked(state):
    path = blocked_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump({"blocked": state}, f)
    os.replace(tmp, path)


def blocked_identities():
    """The identities of the reviewers that are blocked for every head."""
    return set(load_blocked())


def next_probe_at(now, reset_at=None):
    """When a blocked reviewer may be probed next.

    A provider that names a reset time is probed at that time and not
    before it. A block that names no reset is probed an hour later. The
    deadline is set once and moves on after every probe, so a stale
    reset time cannot make the reviewer due for ever."""
    now = time.time() if now is None else now
    if reset_at:
        reset_at = float(reset_at)
        if reset_at > now:
            return reset_at
    return now + PROBE_INTERVAL


def block_reviewer(selection, reason, now=None, reset_at=None):
    """Block a reviewer for every head.

    Returns the log line for the block, or None when the reviewer was
    already blocked: each block is logged once."""
    ident = identity(selection)
    if not ident:
        return None
    with BlockedLock():
        state = load_blocked()
        if ident in state:
            return None
        now = time.time() if now is None else now
        state[ident] = {"at": now, "reason": reason,
                        "probeAt": next_probe_at(now, reset_at), "resetAt": reset_at}
        save_blocked(state)
    return f"blocked reviewer {ident}: {reason}"


def unblock_reviewer(selection):
    """Unblock a reviewer. Returns the log line, or None."""
    ident = identity(selection)
    with BlockedLock():
        state = load_blocked()
        if ident not in state:
            return None
        del state[ident]
        save_blocked(state)
    return f"unblocked reviewer {ident}"


def probe_due(selection, now=None):
    """Whether a blocked reviewer may be probed again.

    One deadline governs the probe: the hour after the last probe, or the
    reset the provider named when that is later. A reset that has passed
    does not make the reviewer due for ever: the deadline moves on after
    every probe."""
    record = load_blocked().get(identity(selection))
    if not record:
        return False
    now = time.time() if now is None else now
    deadline = record.get("probeAt")
    if deadline is None:
        deadline = record.get("resetAt")
    return now >= float(deadline or 0)


def note_probe(selection, request_id, now=None):
    """Record the probe of a blocked reviewer, so the next one waits.

    The reset the provider named is consumed here: the probe it scheduled
    has run, and a failed probe must not re-arm the reviewer against the
    same expired reset. The next probe is an hour away. The record of the
    last failure is cleared, so the failure of this probe is recorded
    once, when it ends."""
    ident = identity(selection)
    with BlockedLock():
        state = load_blocked()
        record = state.get(ident)
        if not record:
            return None
        record["probeAt"] = (time.time() if now is None else now) + PROBE_INTERVAL
        record["probeRequestId"] = request_id
        record["resetAt"] = None
        record["probeFailedAt"] = None
        record["probeFailedRequestId"] = None
        save_blocked(state)
    return record


def note_probe_failure(selection, text, now=None, request_id=None):
    """Record a probe that ended without an answer.

    The failure is recorded once per probe, and its deadline is anchored
    to the failure itself: the next probe waits an hour after the failure,
    or until the reset the provider names in the failure, whichever is
    later. A later tick that reads the same failure again does not move
    the deadline, so a failed probe cannot hold the reviewer blocked for
    ever and cannot bring the next probe forward either."""
    ident = identity(selection)
    with BlockedLock():
        state = load_blocked()
        record = state.get(ident)
        if not record:
            return None
        probe_request = record.get("probeRequestId")
        if request_id is not None and probe_request is not None and request_id != probe_request:
            # The failure is of an older probe. It says nothing about the
            # probe that is current, so the deadline stays where it is.
            return record
        if probe_request is not None and record.get("probeFailedRequestId") == probe_request:
            # This failure is already recorded. Its deadline stays where
            # the failure put it.
            return record
        now = time.time() if now is None else now
        reset_at = reset_time(text, now)
        record["probeAt"] = next_probe_at(now, reset_at)
        record["resetAt"] = reset_at
        record["probeFailedAt"] = now
        record["probeFailedRequestId"] = probe_request
        save_blocked(state)
    return record


def failure_text(payload):
    """The error text of a failed run, from whatever the payload holds."""
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        return " ".join(failure_text(part) for part in payload)
    if not isinstance(payload, dict):
        return ""
    thread = payload.get("thread") if isinstance(payload.get("thread"), dict) else None
    runs = payload.get("recentRuns") or []
    failure = None
    if thread:
        failure = next((run for run in runs
                        if run.get("runId") == thread.get("latestRunId")), thread)
    if failure is None:
        failure = payload
    parts = []
    for field in ("error", "status", "statusCode", "code", "type", "message"):
        value = failure.get(field) if isinstance(failure, dict) else None
        if isinstance(value, dict):
            parts.extend(str(value.get(inner) or "") for inner in ("code", "message", "type"))
        elif value is not None:
            parts.append(str(value))
    if isinstance(payload, dict):
        for item in payload.get("items") or []:
            if item.get("type") in {"error", "run_error", "provider_error"}:
                parts.append(str(item.get("text") or item.get("message") or ""))
    return " ".join(p for p in parts if p)


def failed_reviewer(payload):
    """The reviewer a failed run belonged to, or None."""
    if not isinstance(payload, dict):
        return None
    thread = payload.get("thread") if isinstance(payload.get("thread"), dict) else None
    runs = payload.get("recentRuns") or []
    source = thread
    if thread:
        run = next((r for r in runs if r.get("runId") == thread.get("latestRunId")), None)
        source = run or thread
    if not isinstance(source, dict):
        return None
    instance = source.get("providerInstanceId") or (thread or {}).get("providerInstanceId")
    model = source.get("model") or (thread or {}).get("model")
    if not instance or not model:
        return None
    return {"instanceId": instance, "model": model}


def failure_status(payload):
    """The status of the failed run in a payload, or None."""
    if not isinstance(payload, dict):
        return None
    runs = payload.get("recentRuns") or []
    thread = payload.get("thread") if isinstance(payload.get("thread"), dict) else None
    if thread:
        run = next((r for r in runs if r.get("runId") == thread.get("latestRunId")), None)
        if run:
            return run.get("status")
        return thread.get("status")
    return payload.get("status")


def provider_block_reason(payload):
    """The blocking provider reason in a failure, or None.

    A failure that carries no error text is still a provider failure when
    the run failed without reaching a model and without an answer: the
    provider could not run the review."""
    text = failure_text(payload)
    low = text.lower()
    for marker in BLOCK_MARKERS:
        if marker in low:
            return marker
    for code in BLOCK_CODES:
        if f" {code} " in f" {low} " or f"status {code}" in low or f"code {code}" in low:
            return f"provider error {code}"
    if failure_status(payload) == "failed" and not provider_ran(payload):
        return "the reviewer did not run"
    return None


def reset_time(text, now=None):
    """The epoch seconds of the reset a provider error names, or None.

    A provider that says when its credits come back is probed at that
    time, and not before. The countdown runs from the moment the error
    was read, so the caller can name that moment."""
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


def provider_ran(payload):
    """Whether the failed run reached a model and answered."""
    if not isinstance(payload, dict):
        return False
    runs = payload.get("recentRuns") or []
    thread = payload.get("thread") if isinstance(payload.get("thread"), dict) else {}
    failure = None
    if thread:
        failure = next((run for run in runs
                        if run.get("runId") == thread.get("latestRunId")), thread)
    if failure is None:
        failure = payload
    if failure.get("executedModel"):
        return True
    for item in payload.get("items") or []:
        if item.get("type") == "assistant_message" and (item.get("text") or "").strip():
            return True
    return False
