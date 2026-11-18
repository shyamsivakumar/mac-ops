#!/usr/bin/env python3
"""Prove the overnight shift's GitHub reads: failures are not cached, pages count.

`run`, `run_read` and `health_run` all go through the shared helper. A
failed read must not be stored, or the next identical read answers with a
cached success and a failed list reads as an empty board. A paginated read
must log one usage row per page, or the report understates the shift.

Runs against a fake `gh` on PATH, so it spends no GitHub quota.
"""
import importlib.util
import json
import os
import sys
import tempfile
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OVERNIGHT = ROOT / "coordinator" / "overnight" / "overnight"
BIN = ROOT / "coordinator" / "bin"

scratch = Path(tempfile.mkdtemp(prefix="overnight-cache-proof-"))
fake_bin = scratch / "bin"
fake_bin.mkdir()
fake = fake_bin / "gh"
mode_file = scratch / "mode"
calls = scratch / "calls.log"
usage = scratch / "usage.jsonl"
mode_file.write_text("fail")
fake.write_text(f"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
base = {str(scratch)!r}
with open(os.path.join(base, "calls.log"), "a") as log:
    log.write(" ".join(args) + "\\n")
mode = open(os.path.join(base, "mode")).read().strip()
if mode == "partial":
    print('[{{"number": 1}}]')
    print('[{{"number": 2}}]')
    sys.stderr.write("gh: HTTP 502\\n")
    sys.exit(1)
if mode == "fail":
    sys.stderr.write("gh: HTTP 500\\n")
    sys.exit(1)
pages = [[{{"number": 1}}], [{{"number": 2}}], [{{"number": 3}}]]
if "--paginate" in args and any(
        arg in ("-q", "--jq", "-t", "--template") or arg.startswith(("-q", "-t"))
        for arg in args):
    for name in ("name1", "name2", "name3"):
        print(name)
elif "--include" in args and "--paginate" in args:
    for name in ("name1", "name2", "name3"):
        print("HTTP/2.0 200 OK")
        print("content-type: application/json")
        print()
        print(name)
elif "--slurp" in args:
    print(json.dumps(pages))
else:
    for page in pages:
        print(json.dumps(page))
""")
fake.chmod(0o755)

os.environ.update({
    "OVERNIGHT_GH": str(fake),
    "COORDINATOR_GH_CACHE": "on",
    "COORDINATOR_GH_CACHE_DIR": str(scratch / "cache"),
    "COORDINATOR_GH_USAGE_LOG": str(usage),
    "COORDINATOR_GH_ACCOUNT": "proof",
    "COORDINATOR_CALLER": "overnight",
})
for path in (str(BIN), str(OVERNIGHT.parent)):
    if path not in sys.path:
        sys.path.insert(0, path)

loader = SourceFileLoader("overnight_cache_probe", str(OVERNIGHT))
spec = importlib.util.spec_from_loader(loader.name, loader)
overnight = importlib.util.module_from_spec(spec)
loader.exec_module(overnight)

ok = True


def check(name, condition, detail=""):
    global ok
    ok = ok and bool(condition)
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" ({detail})" if detail else ""))


def calls_made():
    try:
        return len(calls.read_text().splitlines())
    except OSError:
        return 0


def rows():
    try:
        return [json.loads(line) for line in usage.read_text().splitlines()]
    except OSError:
        return []


argv = [str(fake), "api", "--paginate", "--slurp", "repos/a/b/issues?state=open"]
deadline = time.monotonic() + 30

# 1. A failed read is returned as a failure twice: the first failure is not
#    stored, so the second read goes to GitHub again.
before_fail_rows = len(rows())
before = calls_made()
code_one, out_one = overnight.run_read(argv, 10, deadline)
code_two, out_two = overnight.run_read(argv, 10, deadline)
check("a failed read is not cached", calls_made() - before == 2,
      f"calls={calls_made() - before}")
check("both reads report the failure", code_one != 0 and code_two != 0, f"{code_one}/{code_two}")

# A paginated read that fails part way counts the request that failed.
partial_calls = calls_made()
code_partial, _out = overnight.run_read(argv, 10, deadline)
check("a failed pagination still reports a failure", code_partial != 0)
check("a failed pagination counts its failed request",
      len(rows()) - before_fail_rows == 3, f"rows={len(rows()) - before_fail_rows}")

# 1b. A read that fails part way counts the page that succeeded and the
#     request that failed.
mode_file.write_text("partial")
before = len(rows())
code_partial, _out = overnight.run_read(argv, 10, deadline)
check("a partial pagination still reports a failure", code_partial != 0)
check("a partial pagination counts every attempt", len(rows()) - before == 3,
      f"rows={len(rows()) - before}")

# 2. A paginated success logs one row per page.
mode_file.write_text("ok")
before = len(rows())
code, _out = overnight.run_read(argv, 10, deadline)
check("a success is returned", code == 0)
check("a paginated read logs one row per page", len(rows()) - before == 3,
      f"rows={len(rows()) - before}")

# 2b. A write is never cached through this wrapper either, whichever way
#     the body is written. Attached body flags imply POST.
mode_file.write_text("ok")
for flag in ("--field=name=value", "--raw-field=name=value", "-fname=value"):
    write_argv = [str(fake), "api", flag, "repos/a/b/dispatches?ref=main"]
    before = calls_made()
    overnight.run_read(write_argv, 10, deadline)
    overnight.run_read(write_argv, 10, deadline)
    check(f"a write with {flag} is never cached", calls_made() - before == 2,
          f"calls={calls_made() - before}")

# 2c. A formatted paginated read counts its pages from the headers, and the
#     caller still gets only its own output.
formatted = [str(fake), "api", "--paginate", "--jq", ".[].name", "repos/a/b/tags"]
before = len(rows())
code, out = overnight.run_read(formatted, 10, deadline)
check("a formatted paginated read is returned", code == 0)
check("a formatted paginated read is one invocation",
      len(rows()) - before == 1, f"rows={len(rows()) - before}")
check("a formatted paginated read returns only its bodies",
      out.split() == ["name1", "name2", "name3"] and "HTTP/" not in out, repr(out[:40]))

# 3. A succeeded read is cached: the next identical read makes no call.
before = calls_made()
overnight.run_read(argv, 10, deadline)
check("a succeeded read is cached", calls_made() - before == 0,
      f"calls={calls_made() - before}")

# 4. The board command refuses below the API floor instead of returning a
#    success with an empty stdout the tick would parse as an empty board.
import contextlib
import io
from types import SimpleNamespace

original_probe = overnight.gh_gateway.remaining_or_none
overnight.gh_gateway.remaining_or_none = lambda timeout=60: {"core": 10, "graphql": 10}
out, err = io.StringIO(), io.StringIO()
try:
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = overnight.cmd_board(SimpleNamespace(deadline=30, root=None))
finally:
    overnight.gh_gateway.remaining_or_none = original_probe
check("the board refuses below the floor", code != 0, f"exit={code}")
check("the refusal names the floor", "REFUSED" in err.getvalue() and "floor" in err.getvalue(),
      err.getvalue().strip()[:80])
check("the refusal prints no board", out.getvalue().strip() == "",
      repr(out.getvalue()[:40]))

print("PROOF", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
