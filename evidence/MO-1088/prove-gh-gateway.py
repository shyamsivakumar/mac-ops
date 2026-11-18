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
args = [("--paginate" if word == "--paginate=true" else word) for word in sys.argv[1:]]
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
elif ("--include" in args or "-i" in args) and "--paginate" in args and mode != "bodyhttp":
    for name in ("name1", "name2", "name3"):
        print("HTTP/2.0 200 OK")
        print("content-type: application/json")
        print("x-ratelimit-resource: core")
        print()
        print(name)
elif mode == "failfirst" and "--paginate" in args:
    # The first request fails: one attempt, no page printed.
    sys.stderr.write("gh: HTTP 502\\n")
    sys.exit(1)
elif mode == "partial" and "--paginate" in args:
    # Two pages, then the third request fails: three requests were made.
    for page in (["1"], ["2"]):
        print(json.dumps(page))
    sys.stderr.write("gh: HTTP 502\\n")
    sys.exit(1)
elif mode == "numbers" and "--paginate" in args and any(
        arg in ("-q", "--jq", "-t", "--template") or arg.startswith(("-q", "-t"))
        for arg in args):
    # One page, ten numbers: the shape the gate reported.
    for number in range(1, 11):
        print(number)
elif mode == "bodyhttp" and "--paginate" in args and any(
        arg in ("-q", "--jq", "-t", "--template") or arg.startswith(("-q", "-t"))
        for arg in args):
    for name in ("name1", "name2", "name3"):
        print("HTTP/2.0 200 OK")
        print("content-type: text/plain")
        print("x-ratelimit-resource: core")
        print()
        print("HTTP/1.1 200 OK")
        print("Content-Type: text/plain")
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
    print("x-ratelimit-resource: core")
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
        print("x-ratelimit-resource: core")
        print()
        print(body)
elif "--paginate" in args and any(
        arg in ("-q", "--jq", "-t", "--template") or arg.startswith(("-q", "-t"))
        for arg in args):
    for name in ("name1", "name2", "name3"):
        print(name)
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


def run(argv, floor=None, cwd=None, extra_env=None, fresh=False):
    """Run one read in its own process, so the in-process quota cache is fresh."""
    code = f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
result = gh_gateway.run({argv!r}, timeout=20, limit={floor!r}, fresh={fresh!r})
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
check("a formatted paginated read is one invocation",
      len(rows()) - rows_before == 1, f"rows={len(rows()) - rows_before}")
check("a formatted paginated read returns only its bodies",
      formatted.stdout.split() == ["name1", "name2", "name3"]
      and "HTTP/" not in formatted.stdout, repr(formatted.stdout[:40]))

# The short filter flag also takes its value attached, as `-q.[].name`.
rows_before = len(rows())
attached = run(["gh", "api", "--paginate", "-q.[].name", "repos/a/b/tags"])
check("an attached -q filter is one invocation",
      len(rows()) - rows_before == 1, f"rows={len(rows()) - rows_before}")
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

# The 304 renews the short-TTL body, so the next read is served without a
# call even once the ETag file is gone.
for stale in (cache / "etag").glob("*"):
    stale.unlink()
before = calls_made()
renewed = run(single)
check("a 304 renews the body cache", calls_made() - before == 0,
      f"calls={calls_made() - before}")
check("the renewed body is the one that validated",
      renewed.stdout.strip() == '[{"number": 304}]', renewed.stdout.strip()[:40])
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

# A body that starts like a response is user data: it is not a page and it
# is not stripped from the caller's output.
set_mode("bodyhttp")
rows_before = len(rows())
bodyish = run(["gh", "api", "--paginate", "--jq", ".[].body", "repos/a/b/bodies"])
check("body text is never counted or stripped", len(rows()) - rows_before == 1,
      f"rows={len(rows()) - rows_before}")
check("body text is not stripped from the output", bodyish.stdout.count("HTTP/1.1 200 OK") == 3,
      repr(bodyish.stdout[:60]))
set_mode("200")

# A fresh read never comes from the cache and never fills it.
fresh_read = ["gh", "api", "repos/a/b/issues?state=all&per_page=100&page=1"]
before = calls_made()
run(fresh_read, extra_env={"COORDINATOR_GH_CACHE": "on"}, fresh=True)
run(fresh_read, extra_env={"COORDINATOR_GH_CACHE": "on"}, fresh=True)
check("a fresh read always calls", calls_made() - before == 2, f"calls={calls_made() - before}")
before = calls_made()
run(fresh_read)
check("a fresh read refreshes the cache for the next reader", calls_made() - before == 0,
      f"calls={calls_made() - before}")

# Importing the lane driver must not rename the process: overnight's later
# calls stay overnight's, and the lane's own calls say lane_driver.
code = f"""
import sys
sys.path.insert(0, {str(ROOT / 'coordinator' / 'overnight')!r})
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
import lane_driver
before = gh_gateway.caller()
gh_gateway.record(["gh", "api", "repos/a/b/issues?state=open"])
gh_gateway.run(["gh", "api", "repos/a/b/branches?per_page=100"], timeout=20,
               caller_name="lane_driver")
print("CALLER", before)
"""
lane = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                     env={**env, "COORDINATOR_CALLER": "overnight"})
rows_after = [json.loads(line) for line in (scratch / "usage.jsonl").read_text().splitlines()]
check("importing the lane driver does not rename the process",
      "CALLER overnight" in lane.stdout, lane.stdout.strip()[:60] or lane.stderr.strip()[-120:])
check("the lane's own calls are named lane_driver",
      [row["caller"] for row in rows_after[-2:]] == ["overnight", "lane_driver"],
      f"callers={[row['caller'] for row in rows_after[-2:]]}")

# A read whose first request fails made one attempt, not two.
set_mode("failfirst")
rows_before = len(rows())
run(["gh", "api", "--paginate", "repos/a/b/issues?state=open"])
check("a first-request failure is one request", len(rows()) - rows_before == 1,
      f"rows={len(rows()) - rows_before}")

# A read that fails part way still made the request that failed.
set_mode("partial")
rows_before = len(rows())
run(["gh", "api", "--paginate", "repos/a/b/issues?state=open"])
check("a failed pagination counts its failed request",
      len(rows()) - rows_before == 3, f"rows={len(rows()) - rows_before}")
set_mode("200")

# A CLI command that pages internally is not one request: its count is
# unknown, so the report cannot present it as exact.
rows_before = len(rows())
run(["gh", "run", "list", "-R", "a/b", "--limit", "200"])
check("an internally paginated command is marked unknown",
      rows()[rows_before].get("pages") == "unknown", str(rows()[rows_before]))

# The host-level account is read, not a nested `users:` entry.
hosts = scratch / "gh-config"
hosts.mkdir(exist_ok=True)
(hosts / "hosts.yml").write_text(
    "github.com:\n"
    "    users:\n"
    "        old-name:\n"
    "            user: old-name\n"
    "    user: active-name\n")
account = subprocess.run([sys.executable, "-c", f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
print(gh_gateway._hosts_account("github.com"))
"""], capture_output=True, text=True,
    env={**env, "GH_CONFIG_DIR": str(hosts), "COORDINATOR_GH_ACCOUNT": ""}).stdout.strip()
check("the host-level account wins over a nested users entry",
      account == "active-name", account)

# An unfiltered paginated read without --slurp cannot prove its page
# boundaries, so its count is a lower bound; a slurped read can.
plain = subprocess.run([sys.executable, "-c", f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
plain = ["gh", "api", "--paginate", "repos/a/b/issues?state=open"]
slurped = ["gh", "api", "--paginate", "--slurp", "repos/a/b/issues?state=open"]
headers = ["gh", "api", "--paginate", "--include", "repos/a/b/issues?state=open"]
print("PLAIN", gh_gateway.pages_unknown(plain))
print("SLURPED", gh_gateway.pages_unknown(slurped))
print("HEADERS", gh_gateway.pages_unknown(headers))
"""], capture_output=True, text=True, env=env).stdout.split()
check("an unbounded array read is a lower bound",
      plain == ["PLAIN", "True", "SLURPED", "False", "HEADERS", "False"], str(plain))

# `--paginate=1` is the same flag as `--paginate`.
paginate_one = subprocess.run([sys.executable, "-c", f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
argv = ["gh", "api", "--paginate=1", "repos/a/b/issues?state=open"]
print("PAGINATED", gh_gateway.paginated(argv))
print("UNKNOWN", gh_gateway.pages_unknown(argv))
"""], capture_output=True, text=True, env=env).stdout.split()
check("--paginate=1 is recognised as paginate",
      paginate_one == ["PAGINATED", "True", "UNKNOWN", "True"], str(paginate_one))

# `gh issue` and `gh pr` are mixed groups: reads are GraphQL, writes may be
# REST, so a write is reported as `other` rather than guessed.
mixed = subprocess.run([sys.executable, "-c", f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
for argv in (["gh", "issue", "list"], ["gh", "issue", "comment", "9"],
             ["gh", "pr", "merge", "3"], ["gh", "pr", "view"]):
    print(gh_gateway.resource(argv))
"""], capture_output=True, text=True, env=env).stdout.split()
check("a mixed group is classified by its verb",
      mixed == ["graphql", "other", "other", "graphql"], str(mixed))

# `gh repo` is a mixed command: list and view are GraphQL, writes are REST,
# and a subcommand this code does not know is `other`, not core.
import subprocess as _sp
_repo_routes = _sp.run([sys.executable, "-c", f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
for argv in (["gh", "repo", "list"], ["gh", "repo", "view"],
             ["gh", "repo", "create"], ["gh", "repo", "unknowncmd"]):
    print(gh_gateway.resource(argv))
"""], capture_output=True, text=True, env=env).stdout.split()
check("gh repo is classified by subcommand",
      _repo_routes == ["graphql", "graphql", "core", "other"], str(_repo_routes))

# A filtered read that carries the caller's headers counts its blocks: the
# caller asked for them, so the pages are visible even though the bodies are
# formatted, and the text is returned unchanged.
set_mode("bodyhttp")
rows_before = len(rows())
filtered_include = run(["gh", "api", "--include", "--paginate", "--jq", ".[].body",
                        "repos/a/b/bodies"])
check("a filtered header-carrying read is one unknown invocation",
      len(rows()) - rows_before == 1, f"rows={len(rows()) - rows_before}")
check("a filtered header-carrying read keeps its text",
      filtered_include.stdout.count("HTTP/1.1 200 OK") == 3,
      repr(filtered_include.stdout[:40]))
set_mode("200")

# A filter value named `graphql` does not make a REST read GraphQL.
rows_before = len(rows())
run(["gh", "api", "repos/a/b/issues?state=open", "--jq", "graphql"])
check("a --jq value does not change the quota",
      all(row["resource"] == "core" for row in rows()[rows_before:]),
      f"resources={[row['resource'] for row in rows()[rows_before:]]}")

# `--hostname` takes a value, so the endpoint after it is still the
# endpoint: graphql is graphql, search is search, a list is a list.
routes = subprocess.run([sys.executable, "-c", f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
for argv in (["gh", "api", "--hostname", "github.com", "graphql"],
             ["gh", "api", "--hostname", "github.com", "search/issues?q=x"],
             ["gh", "api", "--hostname", "github.com", "repos/a/b/issues?state=open"]):
    print(gh_gateway.endpoint(argv), gh_gateway.resource(argv), gh_gateway.cacheable(argv))
"""], capture_output=True, text=True, env={**env, "COORDINATOR_GH_ACCOUNT": "proof"}).stdout.splitlines()
check("--hostname does not hide the endpoint",
      routes == ["graphql graphql False", "search/issues?q=x search True",
                 "repos/a/b/issues?state=open core True"], str(routes))

# A method attached to another short flag is a method, and an unknown flag
# cluster is never cached.
combined = ["gh", "api", "-iXPOST", "repos/a/b/issues?per_page=100"]
before = calls_made()
run(combined)
run(combined)
check("a combined short-flag write is never cached", calls_made() - before == 2,
      f"calls={calls_made() - before}")

# Silent pagination prints no body, and an error block that printed its own
# headers is already counted; one that did not is added once.
script = (
    "import sys\n"
    f"sys.path.insert(0, {str(BIN)!r})\n"
    "import gh_gateway as g\n"
    "silent = ['gh', 'api', '--paginate', '--silent', 'repos/a/b/issues?state=open']\n"
    "print('SILENT', g.pages_unknown(silent))\n"
    "block = 'HTTP/2.0 502 Bad Gateway\\nx-ratelimit-resource: core\\n\\n'\n"
    "text = 'HTTP/2.0 200 OK\\nx-ratelimit-resource: core\\n\\n[]\\n'\n"
    "print('BLOCK', g._failed_request(silent, True, 2, True, block))\n"
    "print('NOBLOCK', g._failed_request(silent, True, 2, True, text))\n"
)
unit = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env)
print(unit.stderr.strip()[-200:]) if unit.returncode else None
words = unit.stdout.split()
check("silent pagination is unknown", words[:2] == ["SILENT", "True"], str(words))
check("a printed error block is not counted twice", words[2:4] == ["BLOCK", "0"], str(words[2:4]))
check("a missing error block is counted once", words[4:6] == ["NOBLOCK", "1"], str(words[4:6]))

# A cache hit answers without a quota probe, and the report reads the log
# the writer was configured with.
deadline = subprocess.run([sys.executable, "-c", f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway

def boom(*_args, **_kwargs):
    raise AssertionError("the quota was probed for a cache hit")

gh_gateway.api_remaining = boom
gh_gateway.CACHE_DIR.mkdir(parents=True, exist_ok=True)
arg = ["gh", "api", "repos/a/b/issues?state=open"]
gh_gateway.store(arg, "[]")
result = gh_gateway.run(arg, timeout=5, limit=gh_gateway.floor())
print("HIT", result.returncode, result.stdout)
"""], capture_output=True, text=True, env=env)
check("a cache hit does not wait for a quota probe",
      "HIT 0 []" in deadline.stdout, deadline.stdout.strip()[:40] or deadline.stderr.strip()[-120:])

env_log = scratch / "env-usage.jsonl"
env_log.write_text(json.dumps({"ts": time.time() - 30, "caller": "envrun",
                               "resource": "core", "verb": "list"}) + "\n")
report_env = subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "gh-usage-report.py"), "--hours", "1"],
    capture_output=True, text=True,
    env={**env, "COORDINATOR_GH_USAGE_LOG": str(env_log)})
# A paginated search read counts its pages like any other api read.
rows_before = len(rows())
run(["gh", "api", "--paginate", "--slurp", "search/issues?q=repo:a/b+is:issue"])
check("a paginated search read counts its pages",
      len(rows()) - rows_before == 3, f"rows={len(rows()) - rows_before}")

# A filtered search read is one invocation too: ten numbers from one page
# are not ten search requests.
set_mode("numbers")
rows_before = len(rows())
run(["gh", "api", "--paginate", "--jq", ".[].number", "search/issues?q=repo:a/b"])
check("a filtered search read is one invocation", len(rows()) - rows_before == 1,
      f"rows={len(rows()) - rows_before}")
check("a filtered search read is marked unknown",
      rows()[rows_before].get("pages") == "unknown", str(rows()[rows_before]))
set_mode("200")

# A rotation inside the window discards earlier calls, so the totals are a
# lower bound rather than an exact number.
truncated_log = scratch / "truncated.jsonl"
now = time.time()
(scratch / "truncated.jsonl.1").write_text(
    json.dumps({"ts": now - 600, "caller": "kept", "resource": "core", "verb": "list"}) + "\n")
truncated_log.write_text(
    json.dumps({"ts": now - 30, "caller": "active", "resource": "core", "verb": "list"}) + "\n")
truncated = subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "gh-usage-report.py"),
     "--log", str(truncated_log), "--hours", "1"],
    capture_output=True, text=True, env=env)
check("a rotation inside the window makes the total a lower bound",
      "lower bound" in truncated.stdout and "rotation inside the window" in truncated.stdout,
      truncated.stdout.strip().splitlines()[-2:] if truncated.stdout else truncated.stderr[-80:])

# An unreadable log makes the hour incomplete, not quiet.
unreadable = scratch / "unreadable.jsonl"
unreadable.mkdir()
incomplete = subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "gh-usage-report.py"),
     "--log", str(unreadable), "--hours", "1"],
    capture_output=True, text=True, env=env)
check("an unreadable log is reported and fails",
      incomplete.returncode != 0 and "INCOMPLETE" in (incomplete.stdout + incomplete.stderr),
      f"exit={incomplete.returncode}")
absent = subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "gh-usage-report.py"),
     "--log", str(scratch / "never-written.jsonl"), "--hours", "1"],
    capture_output=True, text=True, env=env)
check("an absent log is not a quiet hour",
      absent.returncode != 0 and "INCOMPLETE" in (absent.stdout + absent.stderr),
      f"exit={absent.returncode}")

check("the report defaults to the writer's log path",
      "envrun" in report_env.stdout, report_env.stdout.strip()[:60] or report_env.stderr.strip()[-80:])

# `--silent=true` is the same flag as `--silent`: no body, so the count of
# a paginated read is unknown.
silent_bool = subprocess.run([sys.executable, "-c", f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
argv = ["gh", "api", "--paginate", "--silent=true", "repos/a/b/issues?state=open"]
print("FILTERED", gh_gateway.filtered(argv))
print("UNKNOWN", gh_gateway.pages_unknown(argv))
"""], capture_output=True, text=True, env=env).stdout.split()
check("--silent=true is recognised as silent",
      silent_bool == ["FILTERED", "True", "UNKNOWN", "True"], str(silent_bool))

# The probe and the read share one deadline on a cache miss.
deadline_check = subprocess.run([sys.executable, "-c", f"""
import sys, time
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
seen = {{}}

def slow_probe(timeout=60, host=None):
    time.sleep(1.0)
    return {{"core": 4000, "graphql": 4000}}

def launcher(argv, **kwargs):
    seen["timeout"] = kwargs.get("timeout")
    class R:
        returncode = 0
        stdout = "[]"
        stderr = ""
    return R()

gh_gateway.api_remaining = slow_probe
gh_gateway.set_runner(lambda: launcher)
gh_gateway.run(["gh", "api", "repos/a/b/collaborators?per_page=100"], timeout=6,
               limit=gh_gateway.floor())
print("TIMEOUT", seen.get("timeout"))
"""], capture_output=True, text=True, env=env)
words = deadline_check.stdout.split()
check("the probe leaves the read less than its whole deadline",
      words[:1] == ["TIMEOUT"] and int(words[1]) < 6, str(deadline_check.stdout.strip()[:40]))

# A first-request failure under --include is one attempt, not two.
first_fail = subprocess.run([sys.executable, "-c", f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
argv = ["gh", "api", "--include", "--paginate", "repos/a/b/tags"]
body, count = gh_gateway.settle(argv, "", False, failed=True)
print("COUNT", count)
"""], capture_output=True, text=True, env=env).stdout.split()
check("an include first-request failure is one attempt",
      first_fail == ["COUNT", "1"], str(first_fail))

# The quota sample belongs to the identity that read it: a balance read
# for one token must not set the floor for another.
quota = subprocess.run([sys.executable, "-c", f"""
import json, os, sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway

class R:
    returncode = 0
    stderr = ""
    def __init__(self, remaining):
        self.stdout = json.dumps({{"resources": {{"core": {{"remaining": remaining}},
                                                 "graphql": {{"remaining": remaining}}}}}})

gh_gateway.set_runner(lambda: (lambda argv, **kwargs: R(int(os.environ["GH_TOKEN"]))))
os.environ["GH_TOKEN"] = "3000"
print("ONE", gh_gateway.api_remaining()["core"])
os.environ["GH_TOKEN"] = "100"
print("TWO", gh_gateway.api_remaining()["core"])
"""], capture_output=True, text=True, env=env).stdout.split()
check("the quota cache follows the credential",
      quota == ["ONE", "3000", "TWO", "100"], str(quota))

# The quota key names the account and the gh configuration too, and an
# unknown identity is never reused.
quota_key = subprocess.run([sys.executable, "-c", f"""
import os, sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
os.environ["COORDINATOR_GH_ACCOUNT"] = "one"
first = gh_gateway.quota_key()
os.environ["COORDINATOR_GH_ACCOUNT"] = "two"
second = gh_gateway.quota_key()
os.environ["COORDINATOR_GH_ACCOUNT"] = "one"
os.environ["GH_CONFIG_DIR"] = "/tmp/other-gh"
third = gh_gateway.quota_key()
os.environ["COORDINATOR_GH_ACCOUNT"] = ""
os.environ["GH_CONFIG_DIR"] = "/tmp/no-such-config"
print("ACCOUNT", first != second)
print("CONFIG", first != third)
print("UNKNOWN", gh_gateway.quota_key() == "")
"""], capture_output=True, text=True, env=env).stdout.split()
check("the quota key follows the active account", quota_key[1] == "True", str(quota_key))
check("the quota key follows the gh config dir", quota_key[3] == "True", str(quota_key))
check("an unknown identity is not reused", quota_key[5] == "True", str(quota_key))

# `--web` opens a browser, so it is never cached.
web = subprocess.run([sys.executable, "-c", f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
for argv in (["gh", "pr", "list", "--web"], ["gh", "pr", "list", "--web=true"],
             ["gh", "pr", "list", "--web=1"], ["gh", "pr", "list", "-w"],
             ["gh", "pr", "list", "-w=true"]):
    print("WEB", gh_gateway.cacheable(argv))
"""], capture_output=True, text=True, env=env).stdout.split()
check("--web is never cached in any spelling",
      web == ["WEB", "False"] * 5, str(web))

# An optional read reserves quota for the host it targets, not the default.
host_quota = subprocess.run([sys.executable, "-c", f"""
import json, os, sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
seen = {{}}

class R:
    returncode = 0
    stderr = ""
    def __init__(self, remaining):
        self.stdout = json.dumps({{"resources": {{"core": {{"remaining": remaining}},
                                                 "graphql": {{"remaining": remaining}}}}}})

def fake(argv, **kwargs):
    seen["argv"] = list(argv)
    return R(100 if "other.example" in argv else 3000)

gh_gateway.set_runner(lambda: fake)
os.environ["COORDINATOR_GH_ACCOUNT"] = "proof"
print("PROBE", gh_gateway.api_remaining(host="other.example")["core"])
print("ARGV", "other.example" in seen["argv"])
print("DEFAULT", gh_gateway.api_remaining()["core"])
"""], capture_output=True, text=True, env=env).stdout.split()
check("the quota probe targets the requested host", host_quota[:2] == ["PROBE", "100"], str(host_quota))
check("the probe passes the host to gh", host_quota[2:4] == ["ARGV", "True"], str(host_quota))
check("the default host is probed separately", host_quota[4:6] == ["DEFAULT", "3000"], str(host_quota))

# A host in the repository selector decides the account and its quota.
selector = subprocess.run([sys.executable, "-c", f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
print("R", gh_gateway.argv_host(["gh", "pr", "list", "-R", "ent.example/o/r"]))
print("PLAIN", repr(gh_gateway.argv_host(["gh", "pr", "list", "-R", "o/r"])))
print("HOSTNAME", gh_gateway.argv_host(["gh", "pr", "list", "--hostname", "h.example"]))
print("ATTACHED", gh_gateway.argv_host(["gh", "pr", "list", "-Rent.example/o/r"]))
print("VALUE", repr(gh_gateway.argv_host(["gh", "pr", "list", "--search", "-Release"])))
print("BOTH", gh_gateway.argv_host(["gh", "pr", "list", "-Rent.example/o/r",
                                   "--search", "-Release"]))
print("SHORT", gh_gateway.argv_host(["gh", "pr", "list", "-Rent.example/o/r",
                                    "-S", "-Release"]))
print("SHORTONLY", repr(gh_gateway.argv_host(["gh", "pr", "list", "-S", "-Release"])))
print("RUNALL", gh_gateway.argv_host(["gh", "run", "list", "-a", "-R", "ent.example/o/r"]))
print("RUNWORKFLOW", gh_gateway.argv_host(["gh", "run", "list", "-R", "ent.example/o/r",
                                          "-w", "-Release"]))
print("NOOWNER", repr(gh_gateway.argv_host(["gh", "issue", "list", "-R", "o/r"])))
print("SEARCHSELECTOR", gh_gateway.argv_host(
    ["gh", "pr", "list", "-R", "actual.example/o/r", "--search",
     "-Rother.example/o/r"]))
print("HOSTNAMEFIRST", gh_gateway.argv_host(
    ["gh", "pr", "list", "--hostname", "h.example", "-R", "a.example/o/r"]))
print("HOSTNAMELAST", gh_gateway.argv_host(
    ["gh", "pr", "list", "-R", "a.example/o/r", "--hostname", "h.example"]))
print("REPOFLAG", gh_gateway.argv_host(["gh", "pr", "list", "--repo", "ent.example/o/r"]))
print("REPOEQ", gh_gateway.argv_host(["gh", "pr", "list", "--repo=ent.example/o/r"]))
print("SHORTSELECTOR", gh_gateway.argv_host(
    ["gh", "pr", "list", "-R", "actual.example/o/r", "-S", "-Rother.example/o/r"]))
print("SEARCHHOST", gh_gateway.argv_host(
    ["gh", "pr", "list", "--search", "--hostname=other.example",
     "-R", "actual.example/o/r"]))
print("RUNBRANCH", gh_gateway.argv_host(
    ["gh", "run", "list", "-R", "actual.example/o/r", "-b", "-Rother.example/o/r"]))
print("LASTREPO", gh_gateway.argv_host(
    ["gh", "pr", "list", "--repo", "first.example/o/r", "-R", "second.example/o/r"]))
print("LASTSHORT", gh_gateway.argv_host(
    ["gh", "pr", "list", "-R", "second.example/o/r", "--repo", "first.example/o/r"]))
print("WORKFLOWALL", gh_gateway.argv_host(
    ["gh", "workflow", "list", "-a", "-R", "ent.example/o/r"]))
print("SELBEFORE", gh_gateway.argv_host(
    ["gh", "-R", "actual.example/o/r", "run", "list", "-w", "-Rnightly"]))
print("SELBEFORE2", gh_gateway.argv_host(
    ["gh", "-R", "actual.example/o/r", "run", "list", "-w", "-Rother.example/o/r"]))
print("COMMITVAL", gh_gateway.argv_host(
    ["gh", "run", "list", "-R", "actual.example/o/r", "--commit",
     "-Rother.example/o/r"]))
print("REPOEQSHORT", gh_gateway.argv_host(["gh", "pr", "list", "-R=ent.example/o/r"]))
print("CLUSTERNEXT", gh_gateway.argv_host(
    ["gh", "pr", "list", "-dR", "ent.example/team/repo"]))
print("VERBAFTER", gh_gateway.argv_host(
    ["gh", "run", "-R", "actual.example/o/r", "list", "-w", "-Rother.example/o/r"]))
print("CLUSTER", gh_gateway.argv_host(
    ["gh", "pr", "list", "-dRent.example/team/repo"]))
print("MERGESQUASH", gh_gateway.argv_host(
    ["gh", "pr", "merge", "42", "-s", "-R", "ent.example/team/repo"]))
print("MERGEMETHOD", gh_gateway.argv_host(
    ["gh", "pr", "merge", "42", "-m", "-d", "-R", "ent.example/team/repo"]))
print("MERGEREBASE", gh_gateway.argv_host(
    ["gh", "pr", "merge", "42", "-r", "-R", "ent.example/team/repo"]))
print("MERGEBODY", gh_gateway.argv_host(
    ["gh", "pr", "merge", "42", "-b", "-Rother.example/o/r", "-s",
     "-R", "ent.example/team/repo"]))
print("REVIEWAPPROVE", gh_gateway.argv_host(
    ["gh", "pr", "review", "42", "-a", "-R", "ent.example/team/repo"]))
print("REVIEWCOMMENT", gh_gateway.argv_host(
    ["gh", "pr", "review", "42", "-c", "-b", "ok", "-R", "ent.example/team/repo"]))
print("REVIEWCHANGES", gh_gateway.argv_host(
    ["gh", "pr", "review", "42", "-r", "-R", "ent.example/team/repo"]))
print("CREATEFILL", gh_gateway.argv_host(
    ["gh", "pr", "create", "-f", "-R", "ent.example/team/repo"]))
print("CREATEDRAFT", gh_gateway.argv_host(
    ["gh", "pr", "create", "-d", "-R", "ent.example/team/repo"]))
print("CREATEWEB", gh_gateway.argv_host(
    ["gh", "pr", "create", "-w", "-R", "ent.example/team/repo"]))
print("CREATEEDITOR", gh_gateway.argv_host(
    ["gh", "pr", "create", "-e", "-R", "ent.example/team/repo"]))
"""], capture_output=True, text=True, env=env).stdout.split()
check("a host in -R is the effective host",
      selector == ["R", "ent.example", "PLAIN", "''", "HOSTNAME", "h.example",
                  "ATTACHED", "ent.example", "VALUE", "''", "BOTH", "ent.example",
                  "SHORT", "ent.example", "SHORTONLY", "''", "RUNALL", "ent.example",
                  "RUNWORKFLOW", "ent.example", "NOOWNER", "''",
                  "SEARCHSELECTOR", "actual.example", "HOSTNAMEFIRST", "a.example",
                  "HOSTNAMELAST", "h.example", "REPOFLAG", "ent.example",
                  "REPOEQ", "ent.example", "SHORTSELECTOR", "actual.example",
                  "SEARCHHOST", "actual.example", "RUNBRANCH", "actual.example",
                  "LASTREPO", "second.example", "LASTSHORT", "first.example",
                  "WORKFLOWALL", "ent.example", "SELBEFORE", "actual.example",
                  "SELBEFORE2", "actual.example", "COMMITVAL", "actual.example",
                  "REPOEQSHORT", "ent.example", "CLUSTERNEXT", "ent.example",
                  "VERBAFTER", "actual.example", "CLUSTER", "ent.example",
                  "MERGESQUASH", "ent.example", "MERGEMETHOD", "ent.example",
                  "MERGEREBASE", "ent.example", "MERGEBODY", "ent.example",
                  "REVIEWAPPROVE", "ent.example", "REVIEWCOMMENT", "ent.example",
                  "REVIEWCHANGES", "ent.example",
                  "CREATEFILL", "ent.example", "CREATEDRAFT", "ent.example",
                  "CREATEWEB", "ent.example", "CREATEEDITOR", "ent.example"],
      str(selector))

# A malformed record makes the measurement incomplete, not quiet.
partial_log = scratch / "partial.jsonl"
partial_log.write_text(
    json.dumps({"ts": time.time() - 20, "caller": "kept", "resource": "core",
                "verb": "list"}) + "\n" + '{"ts": 1, "caller": "trunc')
partial = subprocess.run([sys.executable, str(ROOT / "scripts" / "gh-usage-report.py"),
                          "--log", str(partial_log), "--hours", "1"],
                         capture_output=True, text=True, env=env)
check("a malformed record makes the result incomplete",
      partial.returncode != 0 and "kept" in partial.stdout
      and "INCOMPLETE" in (partial.stdout + partial.stderr),
      f"exit={partial.returncode}")

# An explicit selector overrides GH_REPO, including when it names no host.
override = subprocess.run([sys.executable, "-c", f"""
import os, sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
os.environ["GH_REPO"] = "enterprise.example/team/old"
print("TWOPART", repr(gh_gateway.argv_host(["gh", "pr", "list", "-R", "owner/repo"])))
print("NOSEL", gh_gateway.argv_host(["gh", "pr", "list"]))
print("HOSTED", gh_gateway.argv_host(["gh", "pr", "list", "-R", "ent.example/o/r"]))
"""], capture_output=True, text=True, env=env).stdout.split()
check("an explicit selector overrides GH_REPO, host or not",
      override == ["TWOPART", "''", "NOSEL", "enterprise.example", "HOSTED", "ent.example"],
      str(override))

# `-i=true` is the same as `--include`: the caller's headers must survive.
short_bool = subprocess.run([sys.executable, "-c", f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
argv = ["gh", "api", "-i=true", "repos/a/b/issues?state=open"]
print("INCLUDE", gh_gateway.include_requested(argv))
print("CONDITIONAL", gh_gateway.conditional(argv))
"""], capture_output=True, text=True, env=env).stdout.split()
check("-i=true is the include flag",
      short_bool == ["INCLUDE", "True", "CONDITIONAL", "False"], str(short_bool))

# A `--hostname` read is keyed by that host: an unknown host has no account,
# so it is never cached and cannot answer another account's read.
host_read = ["gh", "api", "--hostname", "enterprise.example",
             "repos/a/b/issues?state=open"]
no_account = {"COORDINATOR_GH_ACCOUNT": ""}
before = calls_made()
run(host_read, extra_env=no_account)
run(host_read, extra_env=no_account)
check("an unknown --hostname host is not cached", calls_made() - before == 2,
      f"calls={calls_made() - before}")
check("the --hostname host is in the key",
      subprocess.run([sys.executable, "-c", f"""
import sys
sys.path.insert(0, {str(BIN)!r})
import gh_gateway
one = gh_gateway._key(["gh", "api", "--hostname", "one.example", "repos/a/b/issues?state=open"])
two = gh_gateway._key(["gh", "api", "--hostname", "two.example", "repos/a/b/issues?state=open"])
print("DIFFER", one != two)
"""], capture_output=True, text=True, env=env).stdout.strip() == "DIFFER True")

# A pull's files collection is a list named by the ticket, so it is cached.
rows_before = len(rows())
files_read = ["gh", "api", "repos/a/b/pulls/7/files?per_page=100"]
before = calls_made()
run(files_read)
run(files_read)
check("a pull's files list is cached once", calls_made() - before == 1,
      f"calls={calls_made() - before}")

# `--paginate=true` is the same flag: it must not take the conditional
# path, which would add `--include` and leave headers in the caller's JSON.
set_mode("200")
rows_before = len(rows())
equals_form = run(["gh", "api", "--paginate=true", "repos/a/b/tags?page=1"])
check("--paginate=true is not handled conditionally",
      "HTTP/" not in equals_form.stdout, repr(equals_form.stdout[:40]))
check("--paginate=true counts its pages", len(rows()) - rows_before == 3,
      f"rows={len(rows()) - rows_before}")

# One page of ten numbers is one call, not ten pages.
set_mode("numbers")
rows_before = len(rows())
numeric = run(["gh", "api", "--paginate", "--jq", ".[].number", "repos/a/b/issues"])
check("ten numbers from one page are one call", len(rows()) - rows_before == 1,
      f"rows={len(rows()) - rows_before}")
check("the numeric read keeps its ten values", len(numeric.stdout.split()) == 10,
      f"values={len(numeric.stdout.split())}")
set_mode("200")

# A filtered read that carries the caller's headers is still the caller's
# text: a body printing a status line and an x-ratelimit header is not a page.
set_mode("bodyhttp")
rows_before = len(rows())
run(["gh", "api", "--include", "--paginate", "--jq", ".[].body", "repos/a/b/bodies"])
check("a filtered caller-header read is one unknown invocation",
      len(rows()) - rows_before == 1, f"rows={len(rows()) - rows_before}")
set_mode("200")

# A formatted read is never replayed: one invocation, and its row says the
# page count is unknown. A write with a filter is not sent twice either.
rows_before = len(rows())
before = calls_made()
run(["gh", "api", "--paginate", "--jq", ".[].name", "repos/a/b/tags"])
check("a formatted read is never replayed", calls_made() - before == 1,
      f"calls={calls_made() - before}")
check("a formatted read marks its pages unknown",
      rows()[rows_before].get("pages") == "unknown", str(rows()[rows_before]))

write_filtered = ["gh", "api", "-X", "POST", "--paginate", "--jq", ".[].name",
                  "repos/a/b/dispatches?ref=main"]
before = calls_made()
run(write_filtered)
run(write_filtered)
check("a filtered write is sent once per call", calls_made() - before == 2,
      f"calls={calls_made() - before}")

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
check("a filtered caller-include read is one unknown invocation",
      len(rows()) - rows_before == 1, f"rows={len(rows()) - rows_before}")
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
