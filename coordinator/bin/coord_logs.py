"""Read-only view of the coordinator logs for `coordq logs`."""

import calendar
import glob
import json
import os
import re
import time

import journal

LOOP_DIR = os.environ.get(
    "COORD_LOOP_DIR", os.path.expanduser("~/Code/coordinator/loop")
)
LIB_LOG_DIR = os.environ.get(
    "COORD_LOG_DIR", os.path.expanduser("~/Library/Logs/coordinator")
)
SOURCES = ("ticks", "dispatch", "gatekeep", "spend", "lanes", "journal")
ERROR_LINE = re.compile(
    r"error|failed|timed out|traceback|unreachable|refused", re.IGNORECASE
)
ERROR_EVENTS = {
    "close_failed",
    "refused",
    "alarm_raised",
    "merge_held",
    "round_cap",
    "start_deferred",
}
STAMP = re.compile(r"(\d{4})-(\d\d)-(\d\d)[ T](\d\d):(\d\d)(?::(\d\d))?(Z?)")
SINCE = re.compile(r"^(\d+)([mhd])$")
UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400}
SECRET = re.compile(
    r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}"
    r"|(?i:bearer)\s+[A-Za-z0-9._~+/=-]{12,}"
    r"|(?i:[\w-]*(?:token|secret|password|passwd|key)[\w-]*)[\"']?\s*[=:]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;\"']+))"
)


def redact(text):
    return SECRET.sub("[redacted]", text)


def since_cutoff(value, now):
    match = SINCE.match(value)
    if not match:
        raise ValueError(
            f"--since {value!r}: use a number and m, h or d, like 30m, 1h or 2d"
        )
    return now - int(match.group(1)) * UNIT_SECONDS[match.group(2)]


def line_time(line):
    match = STAMP.search(line)
    if not match:
        return None
    year, month, day, hour, minute, second, utc = match.groups()
    parts = (int(year), int(month), int(day), int(hour), int(minute), int(second or 0), 0, 0, -1)
    return calendar.timegm(parts) if utc else time.mktime(parts)


def recent_text_lines(path, cutoff):
    with open(path, errors="replace") as handle:
        lines = handle.read().splitlines()
    if cutoff is None:
        return lines
    sample = lines[-2000:]
    stamped = sum(line_time(line) is not None for line in sample) * 2 >= len(sample)
    if not stamped:
        return lines if os.path.getmtime(path) >= cutoff else []
    kept, current = [], None
    for line in lines:
        current = line_time(line) or current
        if current is not None and current >= cutoff:
            kept.append(line)
    return kept


def journal_error_lines(cutoff):
    files = sorted(
        glob.glob(os.path.join(journal.journal_dir(), "events-????-??.jsonl"))
    )[-2:]
    if not files:
        raise OSError(f"no journal files in {journal.journal_dir()}")
    rows = []
    for name in files:
        with open(name, errors="replace") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                    stamp, event = float(row["ts"]), row["event"]
                except (ValueError, KeyError, TypeError):
                    continue
                if event in ERROR_EVENTS and (cutoff is None or stamp >= cutoff):
                    rows.append(line.rstrip("\n"))
    return rows


def source_path(name, queue_dir):
    return {
        "ticks": os.path.join(LOOP_DIR, "ticks.log"),
        "dispatch": os.path.join(queue_dir, "dispatch.log"),
        "gatekeep": os.path.join(queue_dir, "gatekeep.log"),
        "spend": os.path.join(queue_dir, "spend.log"),
        "lanes": os.path.join(LIB_LOG_DIR, "lanes.log"),
        "journal": journal.journal_dir(),
    }[name]


def read_source(name, queue_dir, cutoff):
    if name == "journal":
        return journal_error_lines(cutoff)
    lines = recent_text_lines(source_path(name, queue_dir), cutoff)
    return (
        [line for line in lines if ERROR_LINE.search(line)]
        if name == "lanes"
        else lines
    )


def run(names, queue_dir, since, grep, tail, out, err, now=None):
    if tail < 1:
        print(f"coordq logs: --tail {tail}: use 1 or more", file=err)
        return 2
    try:
        cutoff = since_cutoff(since, now or time.time()) if since else None
        pattern = re.compile(grep, re.IGNORECASE) if grep else None
    except (ValueError, re.error) as error:
        print(f"coordq logs: {error}", file=err)
        return 2
    unknown = [name for name in names if name not in SOURCES]
    if unknown:
        print(f"coordq logs: unknown source {unknown[0]!r}; use {', '.join(SOURCES)}", file=err)
        return 2
    failed = False
    for name in names or SOURCES:
        try:
            lines = read_source(name, queue_dir, cutoff)
        except OSError as error:
            print(
                f"coordq logs: {name}: cannot read {source_path(name, queue_dir)}: {error.strerror or error}",
                file=err,
            )
            failed = True
            continue
        if pattern:
            lines = [line for line in lines if pattern.search(line)]
        print(f"== {name} ({len(lines[-tail:])} of {len(lines)} lines) ==", file=out)
        for line in lines[-tail:]:
            print(redact(line), file=out)
    return 1 if failed else 0
