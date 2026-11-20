"""The factory event journal: one append-only JSON line per lifecycle event.

The file is `events-YYYY-MM.jsonl` (UTC month) in `~/Library/Logs/coordinator`,
or in `COORD_JOURNAL_DIR` when that is set. Every writer appends one line with
one `write()` on an `O_APPEND` descriptor under `flock`, so processes that
share no other lock (coordq, the lane, ticket, alarms) never interleave a
line. The file is never rewritten and never rotated by deletion.

A failed write prints one line to stderr and returns: the factory keeps
running when the journal cannot be written, and the scorecard's reconcile
against GitHub catches the missing line.
"""

import fcntl
import json
import os
import re
import sys
import time

VERSION = 1
COMMON = ("repo", "ticket", "pr", "head", "thread", "item", "attempt", "kind")

_REPO = r"(?P<repo>[^#:\s]+)#(?P<n>\d+)"
_HEAD = r"(?P<head>[0-9a-f]{40})"
_TICKET = re.compile(rf"^ticket:{_REPO}:a(?P<attempt>\d+)$")
_HEADED = re.compile(
    rf"^(?P<kind>gate|fix|continue):{_REPO}:{_HEAD}(?::(?P<rest>.+))?$"
)
_ATTEMPT = re.compile(r"^(?P<work>.+):a(?P<attempt>\d+)$")
_WORK_REF = re.compile(_REPO)


def journal_dir():
    return os.environ.get("COORD_JOURNAL_DIR") or os.path.expanduser(
        "~/Library/Logs/coordinator"
    )


def journal_path(now):
    return os.path.join(
        journal_dir(), time.strftime("events-%Y-%m.jsonl", time.gmtime(now))
    )


def emit(event, actor, **fields):
    now = time.time()
    row = {"v": VERSION, "ts": now, "event": event, "actor": actor}
    for key in COMMON:
        row[key] = fields.pop(key, None)
    row["data"] = {**(fields.pop("data", None) or {}), **fields}
    line = json.dumps(row, default=str, separators=(",", ":")) + "\n"
    try:
        os.makedirs(journal_dir(), exist_ok=True)
        fd = os.open(journal_path(now), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, line.encode())
        finally:
            os.close(fd)
    except OSError as exc:
        print(f"journal: {event} not written: {exc}", file=sys.stderr)


def parse_request_id(cid):
    cid = str(cid or "")
    out = {
        "repo": None,
        "ticket": None,
        "pr": None,
        "head": None,
        "attempt": None,
        "kind": "other",
        "data": {},
    }
    match = _TICKET.match(cid)
    if match:
        out.update(
            kind="build",
            repo=match["repo"],
            ticket=int(match["n"]),
            attempt=int(match["attempt"]),
        )
        return out
    match = _HEADED.match(cid)
    if match:
        out.update(kind=match["kind"], repo=match["repo"], head=match["head"])
        out["pr"] = int(match["n"])
        if match["rest"]:
            out["data"]["suffix"] = match["rest"]
        return out
    match = _ATTEMPT.match(cid)
    if match:
        ref = _WORK_REF.search(match["work"])
        if ref:
            out.update(repo=ref["repo"], ticket=int(ref["n"]))
        out.update(attempt=int(match["attempt"]), kind="build")
        out["data"]["request"] = cid
        return out
    if cid:
        out["data"]["request"] = cid
    return out
