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
       "COORDINATOR_GH_ACCOUNT": "proof",
       "COORDINATOR_CALLER": "proof"}

ok = True


def check(name, condition, detail=""):
    global ok
    ok = ok and bool(condition)
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" ({detail})" if detail else ""))


def run(argv, floor=None, cwd=None):
    """Run one read in its own process, so the in-process quota cache is fresh."""
    code = f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
result = gh_gateway.run({argv!r}, timeout=20, limit={floor!r})
sys.stdout.write(result.stdout)
"""
    return subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, env=env, cwd=cwd)


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

pr_list = ["gh", "pr", "list", "-R", "a/b", "--state", "open", "--json", "number"]
issue_list = ["gh", "issue", "list", "-R", "a/b", "--state", "open", "--json", "number"]
before = calls_made()
p1 = run(pr_list)
p2 = run(pr_list)
check("a repeated `gh pr list` runs once", calls_made() - before == 1,
      f"calls={calls_made() - before}")
check("the cached `gh pr list` returns the same body", p1.stdout == p2.stdout)
before = calls_made()
run(issue_list)
run(issue_list)
check("a repeated `gh issue list` runs once", calls_made() - before == 1,
      f"calls={calls_made() - before}")

rows_before = len(rows())
run(["gh", "search", "issues", "--owner", "a", "--state", "open", "--limit", "5",
     "--json", "number"])
searched = rows()[rows_before:]
check("a search is logged under the search quota",
      searched and all(row["resource"] == "search" for row in searched),
      f"resources={[row['resource'] for row in searched]}")
rows_before = len(rows())
run(["gh", "pr", "view", "7", "-R", "a/b", "--json", "state"])
viewed = rows()[rows_before:]
check("a GraphQL command is not logged as core",
      viewed and all(row["resource"] == "graphql" for row in viewed),
      f"resources={[row['resource'] for row in viewed]}")
rows_before = len(rows())
run(["gh", "api", "repos/a/b/labels?per_page=100"])
labeled = rows()[rows_before:]
check("an api read is logged as core",
      labeled and all(row["resource"] == "core" for row in labeled),
      f"resources={[row['resource'] for row in labeled]}")
rows_before = len(rows())
run(["gh", "api", "search/issues?q=repo:a/b+is:issue"])
searched_api = rows()[rows_before:]
check("an api search endpoint is logged as search",
      searched_api and all(row["resource"] == "search" for row in searched_api),
      f"resources={[row['resource'] for row in searched_api]}")
rows_before = len(rows())
run(["gh", "run", "list", "-R", "a/b", "--limit", "5"])
runs = rows()[rows_before:]
check("a REST command is logged as core",
      runs and all(row["resource"] == "core" for row in runs),
      f"resources={[row['resource'] for row in runs]}")

dispatch = ["gh", "api", "-X", "POST", "repos/a/b/dispatches?ref=main"]
before = calls_made()
run(dispatch)
run(dispatch)
check("a write with a query string is never cached", calls_made() - before == 2,
      f"calls={calls_made() - before}")
check("a write is not conditional",
      not any("dispatches" in line and "If-None-Match" in line
              for line in calls.read_text().splitlines()))

check("the usage log names the caller per call", all(row["caller"] == "proof" for row in rows()))

# A header can carry a credential, so no argument may be written down.
secret = "sekrit-token-value"
run(["gh", "api", "-H", f"Authorization: token {secret}", "repos/a/b/labels?per_page=100"])
logged = (scratch / "usage.jsonl").read_text()
check("the usage log holds no credential", secret not in logged and "Authorization" not in logged)
check("the usage log holds no arguments",
      all("command" not in row for row in rows()), "rows carry caller, quota and verb")

# `--method=POST` must not be read as GET: a write is never cached.
before = calls_made()
run(["gh", "api", "--method=POST", "repos/a/b/dispatches?ref=main"])
run(["gh", "api", "--method=POST", "repos/a/b/dispatches?ref=main"])
check("a --method=POST write is never cached", calls_made() - before == 2,
      f"calls={calls_made() - before}")

# The same command in two checkouts is two reads: the cache key names the
# repository, the host and the account.
one = Path(tempfile.mkdtemp(prefix="repo-one-"))
two = Path(tempfile.mkdtemp(prefix="repo-two-"))
listed = ["gh", "issue", "list", "-R", "a/b", "--state", "open", "--json", "number"]
before = calls_made()
run(listed, cwd=str(one))
run(listed, cwd=str(one))
check("the same repo and command is cached once", calls_made() - before == 1,
      f"calls={calls_made() - before}")
before = calls_made()
run(listed, cwd=str(two))
check("a different checkout is a different read", calls_made() - before == 1,
      f"calls={calls_made() - before}")

result = run(fresh, floor=5000)
check("a read below the floor is refused",
      not result.stdout.strip() and "ApiBudgetExhausted" in result.stderr,
      "a quota of 4000 is under 5000")

print("PROOF", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
