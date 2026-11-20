#!/usr/bin/env python3
"""Move fake test rows out of a coordinator journal into a quarantine file.

A unit-test run that was not isolated wrote fixture events into the live
journal. This script takes the journal path and a match rule, backs up the
whole file, writes the matching rows to `<journal stem>.quarantine.jsonl`
beside it, and rewrites the journal without them.

A row matches when any string in it, `head` or a sha inside `data`, is one hex
character repeated 40 times. No real sha looks like that, so the rule needs no
time window and no repo or pull request filter.

The journal's writers (coordinator/bin/journal.py) append under `flock` on
the journal file itself, so this script takes the same exclusive `flock` on
the journal before it reads, and holds it until the rewritten file is in
place. The rewrite replaces the file, so a writer that opened the old file
and was waiting on the lock would append to the replaced copy. After
releasing the lock the script reads whatever landed there and appends it to
the new journal.

The default is a dry run that prints counts only. `--apply` writes.

    quarantine_test_journal_rows.py JOURNAL [--apply]
"""

import argparse
import collections
import fcntl
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

SETTLE_SECONDS = 1.0


FIXTURE_SHA = re.compile(r"^([0-9a-f])\1{39}$")


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


def apply_rewrite(journal, fd, kept, taken):
    stamp = time.strftime("%Y%m%dT%H%M%S")
    backup = journal.with_name(f"{journal.name}.bak-{stamp}")
    shutil.copy2(journal, backup)
    quarantine = journal.with_name(f"{journal.stem}.quarantine.jsonl")
    with open(quarantine, "ab") as out:
        out.write(b"".join(taken))
        out.flush()
        os.fsync(out.fileno())
    size = os.fstat(fd).st_size
    with tempfile.NamedTemporaryFile(
        dir=journal.parent, prefix=f".{journal.name}.", delete=False
    ) as tmp:
        tmp.write(b"".join(kept))
        tmp.flush()
        os.fsync(tmp.fileno())
    shutil.copymode(journal, tmp.name)
    os.replace(tmp.name, journal)
    fcntl.flock(fd, fcntl.LOCK_UN)
    time.sleep(SETTLE_SECONDS)
    os.lseek(fd, size, os.SEEK_SET)
    late = os.read(fd, 1 << 24)
    if late:
        with open(journal, "ab") as out:
            out.write(late)
    return backup, quarantine, late.count(b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("journal", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    fd = os.open(args.journal, os.O_RDONLY)
    fcntl.flock(fd, fcntl.LOCK_EX)
    with os.fdopen(os.dup(fd), "rb") as stream:
        lines = stream.readlines()
    kept, taken = split_lines(lines)
    print(f"journal: {args.journal}")
    print(f"rows: {len(lines)}  matched: {len(taken)}  kept: {len(kept)}")
    print(f"matched by event: {summarize(taken)}")
    if not args.apply:
        print("dry run: nothing written (pass --apply to rewrite)")
        return 0
    backup, quarantine, late = apply_rewrite(args.journal, fd, kept, taken)
    print(f"backup: {backup}")
    print(f"quarantine: {quarantine} (+{len(taken)} rows)")
    print(f"rows appended during the rewrite and carried over: {late}")
    os.close(fd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
