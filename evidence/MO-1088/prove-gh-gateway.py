#!/usr/bin/env python3
"""Prove the shared gh helper: cache hit, 304, status parsing, usage rows.

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
cache = scratch / "cache"
calls = scratch / "calls.log"
fake = scratch / "bin"
fake.mkdir()
mode_file = scratch / "mode"
mode_file.write_text("200")
(fake / "gh").write_text(f"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
base = {str(scratch)!r}
with open(os.path.join(base, "calls.log"), "a") as log:
    log.write(" ".join(args) + "\\n")
mode = open(os.path.join(base, "mode")).read().strip()
if "rate_limit" in args:
    print(json.dumps({{"resources": {{"core": {{"remaining": 4000}},
                                     "graphql": {{"remaining": 4000}}}}}}))
elif "--include" in args:
    if mode == "304":
        print("HTTP/2.0 304 Not Modified")
        print('etag: "v1"')
        print()
    else:
        body = '[{{"number": 304}}]' if mode == "304body" else '[{{"number": 2}}]'
        print("HTTP/2.0 200 OK")
        print('etag: "v2"')
        print()
        print(body)
elif "--paginate" in args:
    pages = [[{{"number": 1}}], [{{"number": 2}}], [{{"number": 3}}]]
    if "--slurp" in args:
        print(json.dumps(pages))
    else:
        for page in pages:
            print(json.dumps(page))
else:
    print('[{{"number": 1}}]')
""")
(fake / "gh").chmod(0o755)

env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}",
       "COORDINATOR_GH_CACHE": "on",
       "COORDINATOR_GH_CACHE_DIR": str(cache),
       "COORDINATOR_GH_USAGE_LOG": str(scratch / "usage.jsonl"),
       "COORDINATOR_CALLER": "proof"}

ok = True


def check(name, condition, detail=""):
    global ok
    ok = ok and bool(condition)
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" ({detail})" if detail else ""))


def run(argv, floor=None):
    """Run one read in its own process, so the in-process quota cache is fresh."""
    code = f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
result = gh_gateway.run({argv!r}, timeout=20, limit={floor!r})
sys.stdout.write(result.stdout)
"""
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)


def calls_made():
    try:
        return len(calls.read_text().splitlines())
    except OSError:
        return 0


def rows():
    try:
        return [json.loads(line) for line in (scratch / "usage.jsonl").read_text().splitlines()]
    except OSError:
        return []


def forget_body_cache():
    """Keep the etag files, drop the body cache, so the next read runs."""
    for path in cache.iterdir():
        if path.is_file():
            path.unlink()


def set_mode(mode):
    mode_file.write_text(mode)


list_read = ["gh", "api", "--paginate", "--slurp", "repos/a/b/issues?state=open"]
single = ["gh", "api", "repos/a/b/issues?state=all&page=1"]
fresh = ["gh", "api", "repos/a/b/other?page=1"]
head = ["gh", "pr", "view", "7", "-R", "a/b", "--json", "state,headRefOid"]

before = calls_made()
rows_before = len(rows())
first = run(list_read)
second = run(list_read)
check("a repeated list read runs once", calls_made() - before == 1,
      f"calls={calls_made() - before}")
check("the cached read returns the same body", first.stdout == second.stdout)
check("a slurped paginated read logs one row per page", len(rows()) - rows_before == 3,
      f"rows={len(rows()) - rows_before}")
rows_before = len(rows())
run(["gh", "api", "--paginate", "repos/a/b/timeline?per_page=100"])
check("an un-slurped paginated read logs one row per page", len(rows()) - rows_before == 3,
      f"rows={len(rows()) - rows_before}")

rows_before = len(rows())
set_mode("200")
a = run(single)
forget_body_cache()
b = run(single)
check("a conditional 200 is counted", len(rows()) - rows_before == 2,
      f"rows={len(rows()) - rows_before}")
check("a conditional 200 returns the new body", a.stdout.strip() == b.stdout.strip() == '[{"number": 2}]')

# A fresh 200 whose body holds the number 304 must not answer the old body.
set_mode("304body")
forget_body_cache()
c = run(single)
check("a 200 body holding 304 returns the new body",
      c.stdout.strip() == '[{"number": 304}]', c.stdout.strip()[:40])

rows_before = len(rows())
set_mode("304")
forget_body_cache()
d = run(single)
check("a 304 answers the stored body", d.stdout.strip() == '[{"number": 304}]', d.stdout.strip()[:40])
check("a 304 is not counted", len(rows()) - rows_before == 0,
      f"rows={len(rows()) - rows_before}")

rows_before = len(rows())
before = calls_made()
set_mode("200")
run(head)
check("a head read always calls", calls_made() - before == 1)
check("a head read is counted", len(rows()) - rows_before == 1)
check("a head read is never conditional",
      not any("headRefOid" in line and "If-None-Match" in line
              for line in calls.read_text().splitlines()))

check("the usage log names the caller per call", all(row["caller"] == "proof" for row in rows()))

result = run(fresh, floor=5000)
check("a read below the floor is refused",
      not result.stdout.strip() and "ApiBudgetExhausted" in result.stderr,
      "a quota of 4000 is under 5000")

print("PROOF", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
