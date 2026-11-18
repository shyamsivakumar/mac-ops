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
import time
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
    if mode == "slow":
        import time as _time
        _time.sleep(5)
    print(json.dumps({{"resources": {{"core": {{"remaining": 4000}},
                                     "graphql": {{"remaining": 4000}}}}}}))
elif "auth" in args:
    print("github.com")
    print("  Token: sekrit-auth-token")
elif ("--include" in args or "-i" in args) and "--paginate" in args:
    for name in ("name1", "name2", "name3"):
        print("HTTP/2.0 200 OK")
        print("content-type: application/json")
        print()
        print(name)
elif mode == "jqerror" and ("--include" in args or "-i" in args):
    print("HTTP/2.0 200 OK")
    print()
    print('[]')
    sys.stderr.write("jq: error: syntax error\\n")
    sys.exit(1)
elif mode == "noetag" and ("--include" in args or "-i" in args):
    print("HTTP/2.0 200 OK")
    print("content-type: application/json")
    print()
    print('[{{"number": 5}}]')
elif "--include" in args or "-i" in args:
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


def run(argv, floor=None, cwd=None, extra_env=None):
    """Run one read in its own process, so the in-process quota cache is fresh."""
    code = f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
result = gh_gateway.run({argv!r}, timeout=20, limit={floor!r})
sys.stdout.write(result.stdout)
"""
    return subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, env={**env, **(extra_env or {})}, cwd=cwd)


def run_quota(timeout):
    """Read the quota through the helper with a bounded timeout."""
    code = f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
print(gh_gateway.remaining_or_none(timeout={timeout!r}))
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

# A formatted, paginated read prints plain text, so the page count comes from
# the response headers and the caller still gets only its own output.
rows_before = len(rows())
formatted = run(["gh", "api", "--paginate", "--jq", ".[].name", "repos/a/b/tags"])
check("a formatted paginated read logs one row per page", len(rows()) - rows_before == 3,
      f"rows={len(rows()) - rows_before}")
check("a formatted paginated read returns only its bodies",
      formatted.stdout.split() == ["name1", "name2", "name3"]
      and "HTTP/" not in formatted.stdout, repr(formatted.stdout[:40]))

# The short filter flag also takes its value attached, as `-q.[].name`.
rows_before = len(rows())
attached = run(["gh", "api", "--paginate", "-q.[].name", "repos/a/b/tags"])
check("an attached -q filter logs one row per page", len(rows()) - rows_before == 3,
      f"rows={len(rows()) - rows_before}")
check("an attached -q filter returns only its bodies",
      attached.stdout.split() == ["name1", "name2", "name3"], repr(attached.stdout[:40]))
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

# The 304 renews the short-TTL body, so the next read is served without
# asking GitHub again even once the ETag file is gone.
import shutil
for path in (cache / "etag").glob("*"):
    path.unlink()
before = calls_made()
renewed = run(single)
check("a 304 renews the body cache", calls_made() - before == 0,
      f"calls={calls_made() - before}")
check("the renewed body is the one that validated", renewed.stdout.strip() == '[{"number": 304}]')
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
# A fallback credential variable changes the identity too.
fallback_read = ["gh", "pr", "list", "-R", "a/b", "--state", "open", "--json", "number"]
before = calls_made()
run(fallback_read, extra_env={"GITHUB_TOKEN": "one"})
run(fallback_read, extra_env={"GITHUB_TOKEN": "one"})
check("a GITHUB_TOKEN identity is cached once", calls_made() - before == 1,
      f"calls={calls_made() - before}")
before = calls_made()
run(fallback_read, extra_env={"GITHUB_TOKEN": "two"})
check("a second GITHUB_TOKEN is a second read", calls_made() - before == 1,
      f"calls={calls_made() - before}")

# The quota probe is bounded by the caller's deadline, not by its own 60 s.
set_mode("slow")
started = time.time()
probe = run_quota(1)
elapsed = time.time() - started
check("a stalled quota probe cannot outlast the caller", probe.stdout.strip() == "None" and elapsed < 4,
      f"stdout={probe.stdout.strip()} elapsed={elapsed:.1f}s")
set_mode("200")

rows_before = len(rows())
run(["gh", "api", "repos/a/b/labels?per_page=100"])
labeled = rows()[rows_before:]
check("an api read is logged as core",
      labeled and all(row["resource"] == "core" for row in labeled),
      f"resources={[row['resource'] for row in labeled]}")
# A repository named `search` is a core endpoint, not the Search API.
rows_before = len(rows())
repo_named_search = run(["gh", "api", "--paginate", "--slurp",
                         "repos/acme/search/issues?per_page=100"], cwd=str(Path(tempfile.mkdtemp())))
check("a repo named search is core", all(row["resource"] == "core" for row in rows()[rows_before:]),
      f"resources={[row['resource'] for row in rows()[rows_before:]]}")
check("a repo named search counts pages", len(rows()) - rows_before == 3,
      f"rows={len(rows()) - rows_before}")

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

# A credential-bearing read is never cached, so its output never reaches disk.
auth = ["gh", "auth", "status", "--show-token"]
before = calls_made()
run(auth)
run(auth)
check("`gh auth status --show-token` is never cached", calls_made() - before == 2,
      f"calls={calls_made() - before}")
leaked = [path for path in cache.rglob("*") if path.is_file() and "sekrit-auth-token" in path.read_text(errors="ignore")]
check("no cache file holds the token", not leaked, f"files={[str(p) for p in leaked]}")

# `--raw-field=name=value` is a body, so the write is never cached.
before = calls_made()
run(["gh", "api", "--raw-field=name=value", "repos/a/b/dispatches?ref=main"])
run(["gh", "api", "--raw-field=name=value", "repos/a/b/dispatches?ref=main"])
check("an attached --raw-field write is never cached", calls_made() - before == 2,
      f"calls={calls_made() - before}")

# Two identities in one checkout are two reads, so one token cannot answer
# another token's read.
identity_read = ["gh", "pr", "list", "-R", "a/b", "--state", "open", "--json", "number"]
before = calls_made()
run(identity_read, extra_env={"GH_TOKEN": "one"})
run(identity_read, extra_env={"GH_TOKEN": "one"})
check("one identity is cached once", calls_made() - before == 1, f"calls={calls_made() - before}")
before = calls_made()
run(identity_read, extra_env={"GH_TOKEN": "two"})
check("a second identity is a second read", calls_made() - before == 1, f"calls={calls_made() - before}")

# A header can carry a credential, so no argument may be written down.
secret = "sekrit-token-value"
run(["gh", "api", "-H", f"Authorization: token {secret}", "repos/a/b/labels?per_page=100"])
logged = (scratch / "usage.jsonl").read_text()
check("the usage log holds no credential", secret not in logged and "Authorization" not in logged)

# The report reads the rotated log too, so a rotation during the measured
# hour does not look like a quiet hour.
report_log = scratch / "report.jsonl"
now = time.time()
(report_log.with_suffix(".jsonl.1")).write_text(json.dumps(
    {"ts": now - 60, "caller": "rotated", "resource": "core", "verb": "list"}) + "\n")
report_log.write_text(
    json.dumps({"ts": now - 30, "caller": "active", "resource": "core", "verb": "list"}) + "\n" +
    json.dumps({"ts": now - 20, "caller": "active", "resource": "core", "verb": "list"}) + "\n")
# The report reads both files under the writer's lock, so a rotation cannot
# land between the two reads.
import fcntl
lock = open(str(report_log) + ".lock", "a")
fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
held = subprocess.Popen(
    [sys.executable, str(ROOT / "scripts" / "gh-usage-report.py"),
     "--log", str(report_log), "--hours", "1"],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
time.sleep(1.0)
blocked = held.poll() is None
fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
lock.close()
report = subprocess.CompletedProcess([], 0, *held.communicate(timeout=30))
check("the report waits for the rotation lock", blocked, "the report ran while the lock was held")
check("the report counts the rotated log too",
      "rotated" in report.stdout and "core total" in report.stdout and " 3 " in report.stdout,
      report.stdout.strip().splitlines()[-3:] if report.stdout else report.stderr.strip()[-80:])

# Rotation is serialised across processes: concurrent writers must not let
# one replace the retained log with the new, nearly empty one.
race_log = scratch / "race-usage.jsonl"
# One rotation across the whole run: 240 rows of about 90 bytes is under
# 24 KiB, so a 12 KiB threshold rotates once and keeps every other row.
race_env = {**env, "COORDINATOR_GH_USAGE_LOG": str(race_log),
            "COORDINATOR_GH_USAGE_MAX": "12000"}
writers = []
for _ in range(6):
    code = f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
gh_gateway.USAGE_LOG = __import__("pathlib").Path({str(race_log)!r})
for _ in range(40):
    gh_gateway.record(["gh", "api", "repos/a/b/issues?state=open"], 1)
"""
    writers.append(subprocess.Popen([sys.executable, "-c", code], env=race_env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
for writer in writers:
    writer.wait(timeout=60)
kept = 0
for path in (race_log, race_log.with_suffix(race_log.suffix + ".1")):
    try:
        kept += len(path.read_text().splitlines())
    except OSError:
        pass
check("concurrent rotation keeps every row", kept == 240, f"rows={kept}")

# A single-page read with no ETag still fills the short-TTL cache, so the
# next identical read inside the window does not spend another core call.
set_mode("noetag")
noetag = ["gh", "api", "repos/a/b/topics?page=1"]
before = calls_made()
first_noetag = run(noetag)
second_noetag = run(noetag)
check("a conditional read with no ETag is cached for the TTL", calls_made() - before == 1,
      f"calls={calls_made() - before}")
check("the cached no-ETag read returns the same body",
      first_noetag.stdout.strip() == second_noetag.stdout.strip() == '[{"number": 5}]',
      repr((first_noetag.stdout, second_noetag.stdout)))
set_mode("200")

# A query string alone is not a list: a single ref read is never cached,
# so a moved branch is never answered from an old body.
set_mode("200")
ref_read = ["gh", "api", "repos/a/b/git/ref/heads/main?per_page=1"]
before = calls_made()
run(ref_read)
run(ref_read)
check("a single-object read with a query is never cached", calls_made() - before == 2,
      f"calls={calls_made() - before}")

# A 2xx that fails locally is not cached either: the first caller sees the
# error and the next identical read must see it too, not a cached success.
set_mode("jqerror")
broken = ["gh", "api", "repos/a/b/broken?page=1"]
before = calls_made()
run(broken)
run(broken)
check("a 2xx with a local error is not cached", calls_made() - before == 2,
      f"calls={calls_made() - before}")
set_mode("200")

# A required read is not optional polling: without a floor it still runs
# when the quota is under the shared floor.
low_env = {**env, "COORDINATOR_GH_FLOOR": "5000"}
code = f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
result = gh_gateway.run(["gh", "api", "repos/a/b/pulls/7"], timeout=20)
print("RAN", result.returncode, bool(result.stdout))
"""
required = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=low_env)
check("a required read runs below the floor", "RAN 0 True" in required.stdout,
      required.stdout.strip()[:40] or required.stderr.strip()[-80:])

# A caller that asks for the headers gets them back untouched, in both
# spellings, and is never handled conditionally.
set_mode("200")
for spelling in ("--include", "-i"):
    included = run(["gh", "api", spelling, "repos/a/b/labels?per_page=100"])
    check(f"caller headers come back with {spelling}", "HTTP/" in included.stdout,
          repr(included.stdout[:40]))
check("a caller-requested header read is not conditional",
      not any("labels" in line and "If-None-Match" in line
              for line in calls.read_text().splitlines()))

# A paginated formatted read that already carries the caller's headers is
# counted from those headers, and its output keeps them.
rows_before = len(rows())
included_pages = run(["gh", "api", "--include", "--paginate", "--jq", ".[].name", "repos/a/b/tags"])
check("a caller-included paginated read logs one row per page",
      len(rows()) - rows_before == 3, f"rows={len(rows()) - rows_before}")
check("a caller-included paginated read keeps its headers",
      included_pages.stdout.count("HTTP/") == 3 and "name1" in included_pages.stdout,
      repr(included_pages.stdout[:40]))

# The same holds with no output filter: the bodies are JSON, but the
# response starts with a status line, so the headers carry the count.
rows_before = len(rows())
unfiltered = run(["gh", "api", "-i", "--paginate", "repos/a/b/tags"])
check("an unfiltered caller-included read logs one row per page",
      len(rows()) - rows_before == 3, f"rows={len(rows()) - rows_before}")
check("an unfiltered caller-included read keeps its headers",
      unfiltered.stdout.count("HTTP/") == 3, repr(unfiltered.stdout[:40]))

# Two writers refreshing one entry use their own temporary file, so the
# entry is always whole.
code = f"""
import json, sys, threading
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
path = gh_gateway.CACHE_DIR / "race-entry.json"

def write(number):
    for _ in range(60):
        gh_gateway._atomic_write(path, json.dumps({{"expiry": 0, "stdout": str(number)}}))

threads = [threading.Thread(target=write, args=(n,)) for n in range(8)]
[t.start() for t in threads]
[t.join() for t in threads]
entry = json.loads(path.read_text())
print("WHOLE", isinstance(entry.get("stdout"), str))
"""
race = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
check("concurrent writers leave a whole entry", "WHOLE True" in race.stdout,
      race.stdout.strip()[:40] or race.stderr.strip()[-80:])
check("the usage log holds no arguments",
      all("command" not in row for row in rows()), "rows carry caller, quota and verb")

# `--method=POST` must not be read as GET: a write is never cached.
before = calls_made()
run(["gh", "api", "--method=POST", "repos/a/b/dispatches?ref=main"])
run(["gh", "api", "--method=POST", "repos/a/b/dispatches?ref=main"])
check("a --method=POST write is never cached", calls_made() - before == 2,
      f"calls={calls_made() - before}")

# gh uses the last method flag, so a repeated flag is a write here too.
before = calls_made()
run(["gh", "api", "-X", "GET", "-X", "POST", "repos/a/b/dispatches?ref=main"])
run(["gh", "api", "-X", "GET", "-X", "POST", "repos/a/b/dispatches?ref=main"])
check("a repeated method flag ending in POST is never cached", calls_made() - before == 2,
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
