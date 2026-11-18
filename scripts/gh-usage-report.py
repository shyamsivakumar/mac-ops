#!/usr/bin/env python3
"""Report the GitHub core calls per caller per hour.

Every coordinator caller writes one JSON line per GitHub call to the shared
usage log through `coordinator/bin/gh_gateway.py`. This reads that log and
prints the count per caller per hour, so the measurement in
`evidence/MO-1088/api-usage.md` can be repeated after a change.

    python3 scripts/gh-usage-report.py --hours 1
    python3 scripts/gh-usage-report.py --hours 24 --log /path/to/gh-usage.jsonl

A cached answer and a 304 are not GitHub calls, so they are not in the log
and not in the count. Each row names the caller, the verb and the quota: `core` for
`gh api`, `search` for `gh search`, `graphql` for the commands GitHub
answers over GraphQL. Only the `core` rows count against the 5000 an hour
the ticket is about.
"""
import argparse
import collections
import json
import os
import time
from datetime import datetime, timezone


def read(path):
    rows = []
    try:
        with open(path) as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and isinstance(row.get("ts"), (int, float)):
                    rows.append(row)
    except FileNotFoundError:
        return rows, "absent"
    except OSError:
        return rows, "error"
    return rows, "ok"


def hour(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:00Z")


def main():
    parser = argparse.ArgumentParser()
    # The writer's own setting decides where the log is; `--log` overrides.
    parser.add_argument("--log", default=os.environ.get(
        "COORDINATOR_GH_USAGE_LOG",
        os.path.expanduser("~/Library/Logs/coordinator/gh-usage.jsonl")))
    parser.add_argument("--hours", type=float, default=1.0,
                        help="how far back to report, in hours")
    args = parser.parse_args()
    since = time.time() - args.hours * 3600
    # The gateway rotates the log when it grows, so the hour being measured
    # can span the active file and the one it was rotated into. Both are
    # read, and both get the same cutoff; dropping the rotation would make
    # a rotation during the hour look like a quiet hour.
    sources = [args.log, args.log + ".1"]
    # The two files are read under the writer's rotation lock. Without it a
    # rotation between the reads counts the old active file twice and
    # misses the new one.
    rows = []
    lock_path = args.log + ".lock"
    try:
        import fcntl
        handle = open(lock_path, "a")
    except (ImportError, OSError):
        handle = None
    try:
        if handle is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
        unreadable = []
        for source in sources:
            found, state = read(source)
            if state == "error":
                unreadable.append(source)
            rows.extend(row for row in found if row["ts"] >= since)
    finally:
        if handle is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
    if unreadable:
        # A log that cannot be read means the hour is incomplete, not quiet:
        # saying so and failing is the only honest result.
        print(f"INCOMPLETE: could not read {', '.join(unreadable)}; "
              f"the counts below cover only the files that could be read")
        if not rows:
            return 2
        incomplete = True
    else:
        incomplete = False
    if not rows:
        print(f"no GitHub calls recorded in the last {args.hours:g}h at {args.log}")
        return 0
    per_hour = collections.Counter(
        (hour(row["ts"]), row.get("caller") or "unknown", row.get("resource") or "core")
        for row in rows)
    per_caller = collections.Counter(
        (row.get("caller") or "unknown", row.get("resource") or "core") for row in rows)
    unknown = sum(1 for row in rows if row.get("pages") == "unknown")
    calls_header = "calls (>=)" if unknown else "calls"
    print(f"{'hour':20} {'caller':16} {'quota':8} {calls_header}")
    for (stamp, caller, quota), count in sorted(per_hour.items()):
        print(f"{stamp:20} {caller:16} {quota:8} {count}")
    print()
    print(f"{'caller':16} {'quota':8} {calls_header:>9} {'per hour':>9}")
    for (caller, quota), count in sorted(per_caller.items()):
        print(f"{caller:16} {quota:8} {count:6} {count / args.hours:9.0f}")
    core = sum(count for (_caller, quota), count in per_caller.items() if quota == "core")
    unknown = sum(1 for row in rows if row.get("pages") == "unknown")
    label = "core total (lower bound)" if unknown else "core total"
    print(f"{label:16} {'core':8} {core:6} {core / args.hours:9.0f}")
    all_label = "all requests (lower bound)" if unknown else "all requests"
    print(f"{all_label:16} {'':8} {len(rows):6} {len(rows) / args.hours:9.0f}")
    if incomplete:
        print("result: incomplete (an input log could not be read)")
        return 2
    if unknown:
        # A formatted paginated read is one measured invocation whose page
        # count cannot be seen. It is named here so a low core total is
        # never mistaken for proof that nothing else was spent.
        print(f"note: {unknown} formatted paginated read(s) counted as one "
              f"request each, page count unknown")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
