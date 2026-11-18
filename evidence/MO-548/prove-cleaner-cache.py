#!/usr/bin/env python3
"""Prove the worktree cleaner's commit cache: save, reload, evict, persist.

The cache keeps a verified `<repo>@<sha>` for a week so a scan does not ask
GitHub again. A refresh that fails must evict the positive entry, and the
eviction must be saved before the cleaner lock is released, or the next scan
reloads the stale positive.

This runs the real `GitHub` class from `scripts/worktree-cleaner/cleaner.py`
against a fake git runner, so it spends no GitHub quota.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLEANER = ROOT / "scripts" / "worktree-cleaner" / "cleaner.py"

spec = importlib.util.spec_from_file_location("cleaner_probe", CLEANER)
cleaner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleaner)

REPO = "shyamsivakumar/mac-ops"
SHA = "a" * 40
KEY = f"{REPO}@{SHA}"
scratch = Path(tempfile.mkdtemp(prefix="cleaner-cache-proof-"))
cache_path = scratch / "github-commits.json"
ok = True
calls = []


def check(name, condition, detail=""):
    global ok
    ok = ok and bool(condition)
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" ({detail})" if detail else ""))


def fake_run(argv, timeout=None):
    calls.append(argv)
    if "commits" in " ".join(argv):
        return subprocess.CompletedProcess(argv, 0, SHA + "\n", "")
    return subprocess.CompletedProcess(argv, 0, "", "")


def fake_missing(argv, timeout=None):
    calls.append(argv)
    return subprocess.CompletedProcess(argv, 1, "", "HTTP 404: Not Found")


cleaner.run = fake_run

# The commit lookup goes through the shared gateway, so it is metered and a
# forced refresh skips the gateway cache.
metered = []


class Result:
    def __init__(self, argv, code, out):
        self.args = argv
        self.returncode = code
        self.stdout = out


def fake_gateway(argv, **kwargs):
    metered.append({"argv": list(argv), **kwargs})
    # The lookup still runs through this file's git runner, so the failure
    # cases below keep their behaviour.
    return cleaner.run(argv, timeout=kwargs.get("timeout", 30))


cleaner.gh_gateway = type("GatewayStub", (), {"run": staticmethod(fake_gateway)})

# 1. A verified commit is a positive, and it is persisted by save_cache.
first = cleaner.GitHub(cache_path)
check("a verified commit is present", first.commit_present(REPO, SHA) is True)
first.save_cache()
saved = json.loads(cache_path.read_text())
check("save_cache persists the positive", saved.get(KEY, 0) > 0, f"entries={sorted(saved)}")

# 1b. The lookup is metered through the shared gateway, and its caller is
#     named, so the cleaner is visible in the per-caller report.
check("the commit lookup is metered", len(metered) == 1 and
      metered[0].get("caller_name") == "worktree-cleaner", str(metered[:1]))
check("an ordinary lookup may use the gateway cache",
      metered[0].get("fresh") is False)
reloaded_refresh = cleaner.GitHub(cache_path)
reloaded_refresh.commit_present(REPO, SHA, refresh=True)
check("a forced refresh skips the gateway cache",
      metered[-1].get("fresh") is True, str(metered[-1]))

# 2. A reload trusts it: no GitHub call is made for the same commit.
calls.clear()
reloaded = cleaner.GitHub(cache_path)
check("a reload serves the positive without a call",
      reloaded.commit_present(REPO, SHA) is True and not calls)

# 3. A failed refresh evicts the positive, and save_cache (the scan's second
#    save, inside the lock) persists the eviction.
cleaner.run = fake_missing
check("a failed refresh evicts the positive", reloaded.commit_present(REPO, SHA, refresh=True) is False)
reloaded.save_cache()
check("the eviction is persisted",
      KEY not in json.loads(cache_path.read_text()), f"entries={sorted(json.loads(cache_path.read_text()))}")

# 4. A later scan does not reload the stale positive: it asks GitHub again.
calls.clear()
later = cleaner.GitHub(cache_path)
check("a later scan asks GitHub again",
      later.commit_present(REPO, SHA) is False and len(calls) == 1, f"calls={len(calls)}")

print("PROOF", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
