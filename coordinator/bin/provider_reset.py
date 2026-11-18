"""The reset a provider error names.

A provider that refuses to run often says when it comes back: "resets in 30
minutes", "retry after 3600s", "resets at 14:00 UTC", "will reset at
2026-11-18 11:58:52". This module reads that sentence and gives the moment
it names, in the zone the sentence states.

A relative reset is measured from the failure, not from the moment the
failure is read: a run that failed at 10:35 and says "resets in 30 minutes"
comes back at 11:05, not at 11:05 plus however long the failure took to
read. An absolute reset is taken as it is written, with its fraction of a
second and its offset read whole.
"""
import re
import time
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python without zoneinfo
    ZoneInfo = None

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
    r"\b(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)(Z|[+-]\d{2}:?\d{2})?\b")
TIME_ONLY = re.compile(r"\b(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?)")
# The words that make a time a reset rather than any time in a message.
RESET_WORD = re.compile(r"reset|retry|available|till|until|back\s+off", re.IGNORECASE)
# The zone a message states for its reset: "UTC", "+08:00", "Asia/Shanghai".
OFFSET = re.compile(r"([+-])(\d{2}):?(\d{2})\b")
NAMED_ZONE = re.compile(r"\b([A-Za-z]+(?:/[A-Za-z_]+)+)\b")

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
    if re.match(r"\s*Z\b", window):
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
    clock, _, fraction = time_text.partition(".")
    if fraction:
        clock = f"{clock}.{fraction[:6].ljust(6, '0')}"
    try:
        moment = datetime.fromisoformat(f"{date_text}T{clock}")
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
