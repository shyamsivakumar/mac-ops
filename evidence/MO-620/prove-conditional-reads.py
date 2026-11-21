#!/usr/bin/env python3
"""Prove gatekeep's list reads are conditional. Usage: prove-conditional-reads.py <repo root>

A stateful fake `gh` on PATH answers If-None-Match with a 304 when the
list is unchanged. It counts the 200 answers, which are the calls that
cost core quota. No GitHub call is made.
"""
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

root = Path(sys.argv[1]).resolve()
scratch = Path(tempfile.mkdtemp(prefix="mo620-proof-"))
fake = scratch / "bin"
fake.mkdir()
db = scratch / "db.json"
(fake / "gh").write_text(f"""#!/usr/bin/env python3
import hashlib, json, os, sys
args = sys.argv[1:]
base = {str(scratch)!r}
if "rate_limit" in args:
    print(json.dumps({{"resources": {{"core": {{"remaining": 4000}}, "graphql": {{"remaining": 4000}}}}}}))
    sys.exit(0)
db = json.load(open(os.path.join(base, "db.json")))
route = next(a for a in args[1:] if a.startswith("repos/"))
path = route.split("?")[0]
rows = db[path]
body = json.dumps(rows)
etag = '"' + hashlib.sha1(body.encode()).hexdigest()[:12] + '"'
sent = next((args[i + 1].split(": ", 1)[1] for i, a in enumerate(args) if a == "-H"), None)
log = open(os.path.join(base, "calls.log"), "a")
if "--include" in args:
    if sent == etag:
        log.write("304 " + route + "\\n")
        print("HTTP/2.0 304 Not Modified")
        print("etag: " + etag)
        print()
        sys.exit(0)
    log.write("200 " + route + "\\n")
    print("HTTP/2.0 200 OK")
    print("etag: " + etag)
    print()
    print(body)
else:
    log.write("200 paginated " + route + "\\n")
    size = int(route.split("per_page=")[1]) if "per_page=" in route else 30
    print(json.dumps([rows[i:i + size] for i in range(0, len(rows), size)] or [[]]))
""")
(fake / "gh").chmod(0o755)

os.environ.update({
    "PATH": f"{fake}:{os.environ['PATH']}",
    "COORDQ_DIR": str(scratch / "queue"),
    "COORD_JOURNAL_DIR": str(scratch / "journal"),
    "COORDINATOR_GH_CACHE": "on",
    "COORDINATOR_GH_CACHE_DIR": str(scratch / "cache"),
    "COORDINATOR_GH_USAGE_LOG": str(scratch / "usage.jsonl"),
    "COORDINATOR_GH_ACCOUNT": "proof",
    "COORDINATOR_CALLER": "proof",
})
(scratch / "queue").mkdir()
sys.path.insert(0, str(root / "coordinator" / "bin"))
loader = importlib.machinery.SourceFileLoader("coordq", str(root / "coordinator" / "bin" / "coordq"))
spec = importlib.util.spec_from_loader("coordq", loader)
coordq = importlib.util.module_from_spec(spec)
loader.exec_module(coordq)
coordq.gh_gateway.LIST_TTL = 0

REPO = "o/r"


def write(state):
    db.write_text(json.dumps(state))


def sha(n, tag):
    return hashlib.sha1(f"{n}{tag}".encode()).hexdigest()


def board(tag="a", extra_comment=False):
    state = {f"repos/{REPO}/pulls": [{"number": n, "head": {"sha": sha(n, tag if n == 2 else "a")}} for n in (1, 2, 3)]}
    for n in (1, 2, 3):
        state[f"repos/{REPO}/issues/{n}/comments"] = [{"id": n}] + ([{"id": 99}] if extra_comment and n == 3 else [])
        state[f"repos/{REPO}/commits/{sha(n, tag if n == 2 else 'a')}/statuses"] = [{"state": "success"}]
    return state


def gatekeep_pass():
    calls = scratch / "calls.log"
    calls.write_text("")
    prs = coordq.gh_json(f"repos/{REPO}/pulls?state=open&per_page=100")
    for pr in prs:
        coordq.gh_json(f"repos/{REPO}/issues/{pr['number']}/comments?per_page=100")
        coordq.gh_json(f"repos/{REPO}/commits/{pr['head']['sha']}/statuses?per_page=100")
    lines = calls.read_text().splitlines()
    return sum(l.startswith("200") for l in lines), sum(l.startswith("304") for l in lines)


ok = True


def check(name, condition, detail):
    global ok
    ok = ok and condition
    print(f"{'PASS' if condition else 'FAIL'} {name} ({detail})")


write(board())
paid, free = gatekeep_pass()
check("first pass reads everything", paid == 7, f"{paid} paid, {free} 304")
paid, free = gatekeep_pass()
check("second pass over unchanged PRs costs 0 rate-limited calls", paid == 0, f"{paid} paid, {free} 304")
write(board(tag="b", extra_comment=True))
paid, free = gatekeep_pass()
check("a new head and a new comment are re-read", paid == 3, f"{paid} paid, {free} 304")
paid, free = gatekeep_pass()
check("the pass after that is free again", paid == 0, f"{paid} paid, {free} 304")

for entry in (scratch / "queue").rglob("*"):
    if entry.is_file() and "etag" in str(entry):
        entry.write_text("{not json")
paid, free = gatekeep_pass()
check("corrupt entries are dropped, gatekeep does not crash", paid == 7, f"{paid} paid, {free} 304")

state = board()
state[f"repos/{REPO}/pulls"] = state[f"repos/{REPO}/pulls"] + [{"number": 4, "head": {"sha": sha(4, "a")}}]
state[f"repos/{REPO}/issues/4/comments"] = []
state[f"repos/{REPO}/commits/{sha(4, 'a')}/statuses"] = []
write(state)
(scratch / "calls.log").write_text("")
rows = coordq.gh_json(f"repos/{REPO}/pulls?state=open&per_page=2")
check("a full page falls back to the paginated read and returns every row", len(rows) == 4,
      f"{len(rows)} rows, calls: {(scratch / 'calls.log').read_text().split(chr(10))[:-1]}")
sys.exit(0 if ok else 1)
