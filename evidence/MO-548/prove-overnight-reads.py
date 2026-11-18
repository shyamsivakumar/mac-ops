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
if mode == "fail":
    sys.stderr.write("gh: HTTP 500\\n")
    sys.exit(1)
pages = [[{{"number": 1}}], [{{"number": 2}}], [{{"number": 3}}]]
if "--slurp" in args:
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
before = calls_made()
code_one, out_one = overnight.run_read(argv, 10, deadline)
code_two, out_two = overnight.run_read(argv, 10, deadline)
check("a failed read is not cached", calls_made() - before == 2,
      f"calls={calls_made() - before}")
check("both reads report the failure", code_one != 0 and code_two != 0, f"{code_one}/{code_two}")

# 2. A paginated success logs one row per page.
mode_file.write_text("ok")
before = len(rows())
code, _out = overnight.run_read(argv, 10, deadline)
check("a success is returned", code == 0)
check("a paginated read logs one row per page", len(rows()) - before == 3,
      f"rows={len(rows()) - before}")

# 3. A succeeded read is cached: the next identical read makes no call.
before = calls_made()
overnight.run_read(argv, 10, deadline)
check("a succeeded read is cached", calls_made() - before == 0,
      f"calls={calls_made() - before}")

print("PROOF", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
