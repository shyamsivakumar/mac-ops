"""One shared provider block record.

A provider that fails for a blocking reason is recorded in one place, so
every caller asks one question: is this provider blocked now? The record of
one provider is

    {"reason": <text>, "since": <ISO UTC>, "until": <ISO UTC>, "by": <writer>}

`since` is the moment the run failed, never the moment the failure was read
and never the moment the run started: a run that began at 10:00 and failed
at 10:35 says nothing about 10:35 through its start. `until` is the reset
the provider named, or an hour after the failure when it named none.

The parts live beside this module: `provider_store` holds the file and its
lock, `provider_refusal` decides whether a failure is the provider refusing,
and `provider_reset` reads the reset a failure names.
"""
import time

from provider_refusal import error_of, failed_at, failure_of, provider_refusal
from provider_reset import reset_at
from provider_store import (failure_time_of, locked, read, stamp, until_of,
                            write)

BLOCK_SECONDS = 3600.0

def identity(selection):
    """The name of one provider: the instance and the last segment of the model.

    The model is compared on its last segment, so a provider-prefixed
    spelling ("zai/glm-5.3") blocks the same provider as the plain one."""
    if not isinstance(selection, dict):
        return ""
    instance = selection.get("instanceId")
    model = str(selection.get("model") or "").split("/")[-1]
    return f"{instance}:{model}" if instance and model else ""


def record_block(selection, reason, failed=None, now=None, by="provider_block"):
    """Block one provider and return the record written, or None.

    The block runs from the moment the run failed to the reset the provider
    named, or to an hour after the failure when it named none.

    A failure read late never replaces a newer failure's record. A newer
    failure always replaces an older one, even when its reset is sooner or
    has already passed, and it is written even when the provider has no
    record yet: an 11:00 "retry after 0s" frees a provider that a 10:00
    refusal held until 14:00, and the passed expiry is kept so a late
    replay of the 10:00 refusal cannot bring the block back. A record whose
    reset has passed blocks nobody."""
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
