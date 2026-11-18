"""Whether a failed run is the provider refusing to run.

The provider's own error code is evidence, and a number inside a message is
not: `worker 14031 exited` holds the digits of 403 and is no refusal. A
local error is not the provider either: `disk quota exceeded` holds the
words of a quota refusal and is a full disk.
"""
import re

from provider_store import parse_time

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



