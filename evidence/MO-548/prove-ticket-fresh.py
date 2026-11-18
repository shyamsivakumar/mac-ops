#!/usr/bin/env python3
"""Prove the ticket tool asks for a fresh list when it must.

A key is allocated from the repository's issue list, and the board's
`--fresh` list must not be built from a cached one. Both read through the
shared gateway, which caches list reads for 120 s, so both must pass
`fresh=True` through it.

The ticket CLI is loaded by path, as the tests do, and the gateway's
`run` is replaced with a recorder, so no GitHub call is made.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "coordinator" / "bin"
TICKET = BIN / "ticket"

sys.path.insert(0, str(BIN))
loader = SourceFileLoader("ticket_fresh_probe", str(TICKET))
spec = importlib.util.spec_from_loader(loader.name, loader)
ticket = importlib.util.module_from_spec(spec)
loader.exec_module(ticket)

ticket.CACHE_DIR = tempfile.mkdtemp(prefix="ticket-fresh-proof-")
calls = []


class Result(subprocess.CompletedProcess):
    pass


def fake_run(argv, **kwargs):
    calls.append({"argv": list(argv), **kwargs})
    endpoint = next((word for word in argv if word.startswith("repos/")), "")
    if "--slurp" in argv:
        body = json.dumps([[]])
    elif "state=all" in endpoint:
        body = "[]"
    else:
        body = "[]"
    return Result(argv, 0, body, "")


ticket.gh_gateway.run = fake_run
ok = True


def check(name, condition, detail=""):
    global ok
    ok = ok and bool(condition)
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" ({detail})" if detail else ""))


# The key allocation scan is always fresh.
calls.clear()
ticket.repo_issues("shyamsivakumar/mac-ops")
check("the key scan reads fresh", calls and all(call.get("fresh") is True for call in calls),
      f"fresh={[call.get('fresh') for call in calls]}")

# `ticket list --fresh` carries the request through to the gateway.
calls.clear()
cfg = {"repos": {"shyamsivakumar/mac-ops": {}}, "labels": {"stage": ["todo"],
       "priority": ["1"], "type": ["chore"]}, "models": {}}
ticket.fetch_list(cfg, fresh=True)
check("a fresh board list reads fresh",
      calls and all(call.get("fresh") is True for call in calls),
      f"fresh={[call.get('fresh') for call in calls]}")

# A cached board list does not: the caller did not ask for fresh.
calls.clear()
ticket.fetch_list(cfg)
check("an ordinary board list may use the cache",
      calls and all(call.get("fresh") is False for call in calls),
      f"fresh={[call.get('fresh') for call in calls]}")

print("PROOF", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
