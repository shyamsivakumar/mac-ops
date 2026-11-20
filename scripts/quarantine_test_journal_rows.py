#!/usr/bin/env python3
"""Move fake test rows out of a coordinator journal into a quarantine file.

A unit-test run that was not isolated wrote fixture events into the live
journal. This script takes the journal path and a match rule, backs up the
whole file, writes the matching rows to `<journal stem>.quarantine.jsonl`
beside it, and rewrites the journal without them.

A row matches when any string in it, `head` or a sha inside `data`, is one hex
character repeated 40 times, or a character repeated 8 times followed by a
character repeated 32 times. No real sha looks like that, so the rule needs no
time window and no repo or pull request filter.

The journal's writers (coordinator/bin/journal.py) append with `O_APPEND` under
`flock` on the journal file itself. This script takes the same exclusive
`flock`, reads the journal, writes the backup and the quarantine file, then
rewrites the same file in place (seek to 0, write the kept rows, truncate)
before it releases the lock. The file is never replaced, so a writer that is
waiting on the lock appends to the same file after the rewrite and no event is
lost.

The default is a dry run that prints counts only. `--apply` writes.

    quarantine_test_journal_rows.py JOURNAL [--apply]
"""

import argparse
import collections
import fcntl
import json
import os
import re
import sys
import time
from pathlib import Path

FIXTURE_SHA = re.compile(r"^([0-9a-f])\1{39}$|^([0-9a-f])\2{7}([0-9a-f])\3{31}$")


def carries_fixture_sha(value):
    if isinstance(value, str):
        return bool(FIXTURE_SHA.match(value))
    if isinstance(value, dict):
        return any(carries_fixture_sha(item) for item in value.values())
    if isinstance(value, list):
        return any(carries_fixture_sha(item) for item in value)
    return False


def split_lines(lines):
    kept, taken = [], []
    for line in lines:
        (taken if carries_fixture_sha(json.loads(line)) else kept).append(line)
    return kept, taken


def summarize(taken):
    by_event = collections.Counter(json.loads(line)["event"] for line in taken)
    return ", ".join(f"{event}={count}" for event, count in sorted(by_event.items()))


def write_synced(path, data, mode="wb"):
    with open(path, mode) as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())


def apply_rewrite(journal, stream, lines, kept, taken):
    backup = journal.with_name(f"{journal.name}.bak-{time.strftime('%Y%m%dT%H%M%S')}")
    write_synced(backup, b"".join(lines))
    quarantine = journal.with_name(f"{journal.stem}.quarantine.jsonl")
    write_synced(quarantine, b"".join(taken), "ab")
    stream.seek(0)
    stream.write(b"".join(kept))
    stream.truncate()
    stream.flush()
    os.fsync(stream.fileno())
    return backup, quarantine


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("journal", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    stream = open(args.journal, "r+b")
    fcntl.flock(stream, fcntl.LOCK_EX)
    lines = stream.readlines()
    kept, taken = split_lines(lines)
    print(f"journal: {args.journal}")
    print(f"rows: {len(lines)}  matched: {len(taken)}  kept: {len(kept)}")
    print(f"matched by event: {summarize(taken)}")
    if not args.apply:
        print("dry run: nothing written (pass --apply to rewrite)")
        return 0
    backup, quarantine = apply_rewrite(args.journal, stream, lines, kept, taken)
    print(f"backup: {backup}")
    print(f"quarantine: {quarantine} (+{len(taken)} rows)")
    stream.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
