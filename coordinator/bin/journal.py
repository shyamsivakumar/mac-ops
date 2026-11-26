"""The factory event journal: one append-only JSON line per lifecycle event.

The file is `events-YYYY-MM.jsonl` (UTC month) in
`~/.local/state/coordinator/journal`, or in `COORD_JOURNAL_DIR` when that is
set. Every writer appends one line with
one `write()` on an `O_APPEND` descriptor under `flock`, so processes that
share no other lock (coordq, the lane, ticket, alarms) never interleave a
line. The file is never rewritten and never rotated by deletion.

A failed write prints one line to stderr and returns: the factory keeps
running when the journal cannot be written, and the scorecard's reconcile
against GitHub catches the missing line.
"""

import fcntl
import functools
import glob
import hashlib
import json
import os
import re
import sys
import time

VERSION = 1
INBOX_WAIT = 2
LEGACY_DIR = "~/Library/Logs/coordinator"
DEFAULT_DIR = "~/.local/state/coordinator/journal"
_MIGRATED = set()
COMMON = (
    "repo",
    "ticket",
    "pr",
    "head",
    "thread",
    "item",
    "attempt",
    "kind",
    "model",
    "arm",
)

_REPO = r"(?P<repo>[^#:\s]+)#(?P<n>\d+)"
_HEAD = r"(?P<head>[0-9a-f]{40})"
_TICKET = re.compile(rf"^ticket:{_REPO}:a(?P<attempt>\d+)$")
_HEADED = re.compile(
    rf"^(?P<kind>gate|fix|continue):{_REPO}:{_HEAD}(?::(?P<rest>.+))?$"
)
_ATTEMPT = re.compile(r"^(?P<work>.+):a(?P<attempt>\d+)$")
_WORK_REF = re.compile(_REPO)


def _merge_file(src, dest):
    with open(src) as fh:
        lines = fh.readlines()
    if os.path.exists(dest):
        seen = set(lines)
        with open(dest) as fh:
            lines += [line for line in fh.readlines() if line not in seen]
    tmp = dest + ".tmp"
    with open(tmp, "w") as fh:
        fh.writelines(lines)
    os.replace(tmp, dest)


def _migrate_legacy(new, old):
    if not os.path.isdir(old):
        return
    marker = os.path.join(new, ".migrated")
    if os.path.exists(marker):
        return
    os.makedirs(new, exist_ok=True)
    with open(os.path.join(new, ".migrate.lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if os.path.exists(marker):
            return
        for path in glob.glob(os.path.join(old, "events-*.jsonl")):
            _merge_file(path, os.path.join(new, os.path.basename(path)))
        open(marker, "w").close()


def journal_dir():
    override = os.environ.get("COORD_JOURNAL_DIR")
    if override:
        return override
    new = os.path.expanduser(DEFAULT_DIR)
    if new not in _MIGRATED:
        _MIGRATED.add(new)
        _migrate_legacy(new, os.path.expanduser(LEGACY_DIR))
    return new


def journal_path(now):
    return os.path.join(
        journal_dir(), time.strftime("events-%Y-%m.jsonl", time.gmtime(now))
    )


@functools.lru_cache(maxsize=1)
def installation_receipt():
    path = os.path.expanduser("~/.local/state/mac-ops/coordinator-installation.json")
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        return json.load(fh)


def installed_sha():
    return installation_receipt().get("source_sha")


_NOTED = set()


def _note(message):
    if message not in _NOTED:
        _NOTED.add(message)
        print(f"journal: {message}", file=sys.stderr)


def _valid_experiments(entries):
    kept = {}
    for entry in entries if isinstance(entries, list) else []:
        ok = (isinstance(entry, dict) and isinstance(entry.get("name"), str)
              and entry.get("side") in ("builder", "gate")
              and isinstance(entry.get("split"), (int, float)) and not isinstance(entry["split"], bool))
        if not ok:
            _note(f"experiment skipped, needs a name, a side of builder or gate and a numeric split: {entry!r}")
        elif entry["side"] in kept:
            _note(f"experiment {entry['name']} refused, {kept[entry['side']]['name']} is already active on side {entry['side']}")
        else:
            kept[entry["side"]] = entry
    return list(kept.values())


def factory_experiments():
    here = os.path.dirname(os.path.realpath(__file__))
    for candidate in (os.path.join(here, "..", "config", "factory.json"), os.path.expanduser("~/.coordinator/factory.json")):
        if os.path.exists(candidate):
            try:
                with open(candidate) as fh:
                    return _valid_experiments(json.load(fh).get("experiments", []))
            except (OSError, ValueError, AttributeError) as exc:
                _note(f"{candidate} unreadable, no experiment registered: {exc}")
                return []
    return []


def arm_for(cluster_root, experiment):
    if not experiment:
        return "control"
    bucket = int(hashlib.sha256((experiment["name"] + cluster_root).encode()).hexdigest(), 16) % 100
    return "treatment" if bucket < experiment["split"] else "control"


def treatment_names(arm, side, name):
    return arm == "treatment" and any(
        e["side"] == side and name in (e.get("names") if isinstance(e.get("names"), list) else [])
        for e in factory_experiments())


def arms_for(cluster_root):
    sides = {"builder": "arm", "gate": "gate_arm"}
    return {sides[e["side"]]: arm_for(cluster_root, e) for e in factory_experiments()}


def assigned_arm(repo, ticket, gate=False):
    if not factory_experiments():
        return None
    try:
        number = int(ticket)
    except (TypeError, ValueError):
        return None
    for path in sorted(glob.glob(os.path.join(journal_dir(), "events-*.jsonl")), reverse=True):
        try:
            with open(path) as fh:
                lines = fh.readlines()
        except (OSError, ValueError):
            continue
        for line in reversed(lines):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("event") == "assigned" and row.get("repo") == repo and row.get("ticket") == number:
                return (row.get("data") or {}).get("gate_arm") if gate else row.get("arm")
    return None


def emit(event, actor, **fields):
    now = time.time()
    row = {"v": VERSION, "ts": now, "event": event, "actor": actor}
    for key in COMMON:
        row[key] = fields.pop(key, None)
    row["data"] = {**(fields.pop("data", None) or {}), **fields}
    row["data"]["sha"] = installed_sha()
    row["data"]["manifest"] = installation_receipt().get("manifest", {}).get(row["arm"] or "control")
    if os.environ.get("COORD_TICK_RUN"):
        row["data"]["via_tick"] = True
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
    else:
        if os.environ.get("COORD_INBOX_HOOK") == "on":
            _record_inbox(row)


def _record_inbox(row):
    try:
        import inbox
        inbox.record_journal(row, wait=INBOX_WAIT)
    except Exception as exc:
        print(f"journal: {row['event']} not queued: {exc}", file=sys.stderr)


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
