"""The gate reviewer chain, its positions and its blocked state.

One list of reviewers serves every gate. A gate that ends without a
verdict moves down the chain, one reviewer per head, and waits when the
chain is exhausted. A reviewer that fails for a blocking provider reason
(no credits, usage limit, auth) is blocked for every head: new gates
start on the next reviewer until it recovers (Shyam 2026-11-17 18:15 PT).
"""

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

# The chain, in order: the OpenAI API on API credits first, the Codex
# subscription second. The planned tail is the Anthropic API on Opus 5.5
# once that instance exists, then the Claude Agent on Opus 5.5. It is not
# in the chain yet: a gate runs on GPT-6.2 Astra only (Shyam 2026-11-17)
# and the merge acceptance accepts no other reviewer.
REVIEWER_CHAIN = (
    {"instanceId": "openai-api", "model": "openai/gpt-6.2-astra"},
    {"instanceId": "codex", "model": "gpt-6.2-astra"},
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
    """The identity of a reviewer selection."""
    if not isinstance(selection, dict):
        return ""
    return f"{selection.get('instanceId')}:{selection.get('model')}"


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
    with open(path + ".tmp", "w") as f:
        json.dump({"blocked": state}, f)
    os.replace(path + ".tmp", path)


def blocked_identities():
    """The identities of the reviewers that are blocked for every head."""
    return set(load_blocked())


def block_reviewer(selection, reason, now=None, reset_at=None):
    """Block a reviewer for every head.

    Returns the log line for the block, or None when the reviewer was
    already blocked: each block is logged once."""
    ident = identity(selection)
    if not ident:
        return None
    state = load_blocked()
    if ident in state:
        return None
    now = time.time() if now is None else now
    state[ident] = {"at": now, "reason": reason,
                    "probeAt": now + PROBE_INTERVAL, "resetAt": reset_at}
    save_blocked(state)
    return f"blocked reviewer {ident}: {reason}"


def unblock_reviewer(selection):
    """Unblock a reviewer. Returns the log line, or None."""
    ident = identity(selection)
    state = load_blocked()
    if ident not in state:
        return None
    del state[ident]
    save_blocked(state)
    return f"unblocked reviewer {ident}"


def probe_due(selection, now=None):
    """Whether a blocked reviewer may be probed again."""
    record = load_blocked().get(identity(selection))
    if not record:
        return False
    now = time.time() if now is None else now
    reset = record.get("resetAt")
    if reset and now >= float(reset):
        return True
    return now >= float(record.get("probeAt") or 0)


def note_probe(selection, request_id, now=None):
    """Record the probe of a blocked reviewer, so the next one waits."""
    ident = identity(selection)
    state = load_blocked()
    record = state.get(ident)
    if not record:
        return None
    record["probeAt"] = (time.time() if now is None else now) + PROBE_INTERVAL
    record["probeRequestId"] = request_id
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


def reset_time(text):
    """The epoch seconds of the reset a provider error names, or None.

    A provider that says when its credits come back is probed at that
    time, and not before."""
    if not isinstance(text, str) or not text:
        return None
    match = re.search(r"resets?\s+in\s+(\d+)\s*(minutes?|mins?|hours?|hrs?)", text, re.I)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        seconds = amount * 3600 if unit.startswith(("hour", "hr")) else amount * 60
        return time.time() + seconds
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
