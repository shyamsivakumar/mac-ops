#!/usr/bin/env python3
"""Prove the shared gh helper: cache hit, 304, usage log and floor.

Runs against a fake `gh` on PATH, so it spends no GitHub quota. Every
assertion is one line of the proof the gate reads.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "coordinator" / "bin"

scratch = Path(tempfile.mkdtemp(prefix="gh-gateway-proof-"))
calls = scratch / "calls.log"
fake = scratch / "bin"
fake.mkdir()
(fake / "gh").write_text(f"""#!/bin/sh
echo "$@" >> {calls}
case "$*" in
  *rate_limit*) echo '{{"resources": {{"core": {{"remaining": 4000}}, "graphql": {{"remaining": 4000}}}}}}' ;;
  *If-None-Match*) echo "HTTP/2.0 304 Not Modified"; echo "etag: \\"v1\\""; echo; printf 'should-not-be-used' ;;
  *--include*) echo "HTTP/2.0 200 OK"; echo "etag: \\"v1\\""; echo; printf '[{{"number": 1}}]' ;;
  *) printf '[{{"number": 1}}]' ;;
esac
""")
(fake / "gh").chmod(0o755)
env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}",
       "COORDINATOR_GH_CACHE": "on",
       "COORDINATOR_GH_CACHE_DIR": str(scratch / "cache"),
       "COORDINATOR_GH_USAGE_LOG": str(scratch / "usage.jsonl"),
       "COORDINATOR_CALLER": "proof"}
read = ["gh", "api", "--paginate", "--slurp", "repos/a/b/issues?state=open&per_page=100"]
single = ["gh", "api", "repos/a/b/issues?state=all&per_page=100&page=1"]
head = ["gh", "pr", "view", "7", "-R", "a/b", "--json", "state,headRefOid"]


def run(argv, source=None):
    code = f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
result = gh_gateway.run({argv!r}, timeout=20)
sys.stdout.write(result.stdout)
"""
    if source:
        code += source
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)


def count():
    try:
        return len(calls.read_text().splitlines())
    except OSError:
        return 0


ok = True


def check(name, condition, detail=""):
    global ok
    ok = ok and bool(condition)
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" ({detail})" if detail else ""))


before = count()
first = run(read)
second = run(read)
check("list read runs once", count() - before == 1, f"calls={count() - before}")
check("cached read returns the same body", first.stdout == second.stdout == '[{"number": 1}]')

before = count()
a = run(single)
b = run(single)
check("single-page read is conditional", "If-None-Match" in calls.read_text() or
      "--include" in calls.read_text(), "the helper sent --include")
check("304 serves the stored body", a.stdout.strip() == b.stdout.strip() == '[{"number": 1}]')

before = count()
run(head)
check("a head read always calls", count() - before == 1)
check("a head read is never conditional",
      "headRefOid" in calls.read_text() and
      not any("If-None-Match" in line for line in calls.read_text().splitlines()
              if "headRefOid" in line))

log = [json.loads(line) for line in (scratch / "usage.jsonl").read_text().splitlines()]
check("usage log names the caller per call", all(row["caller"] == "proof" for row in log) and len(log) == 2,
      f"rows={len(log)}")
check("a cached or 304 answer is not charged as a core call", len(log) == 2,
      "the list hit and the 304 added no row")

low = {**env, "COORDINATOR_GH_FLOOR": "5000"}
code = f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
try:
    gh_gateway.run({read!r}, timeout=20, limit=5000)
except gh_gateway.ApiBudgetExhausted as exc:
    print("EXHAUSTED", exc)
"""
result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=low)
check("a read below the floor is refused", "EXHAUSTED" in result.stdout, result.stdout.strip()[:80] or result.stderr.strip()[:80])

print("PROOF", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
