#!/usr/bin/env python3
"""Prove an explicit `coordq gate` reads without the polling floor.

`gh_json` takes the floor for the gatekeep scan that runs on a timer. An
operator's explicit `gate` is a required read: with 1499 calls left it must
still queue. The gateway's run is replaced with a recorder, so no GitHub
call is made.
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
COORDQ = BIN / "coordq"

sys.path.insert(0, str(BIN))
loader = SourceFileLoader("coordq_floor_probe", str(COORDQ))
spec = importlib.util.spec_from_loader(loader.name, loader)
coordq = importlib.util.module_from_spec(spec)
loader.exec_module(coordq)

calls = []


class Result:
    def __init__(self, argv, code, out):
        self.args = argv
        self.returncode = code
        self.stdout = out
        self.stderr = ""


def fake_run(argv, **kwargs):
    calls.append({"argv": list(argv), **kwargs})
    return Result(argv, 0, "[]")


coordq.gh_gateway.run = fake_run
ok = True


def check(name, condition, detail=""):
    global ok
    ok = ok and bool(condition)
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" ({detail})" if detail else ""))


# The polling scan keeps the floor.
coordq.gh_json("repos/o/r/commits/abc/statuses?per_page=100")
check("the polling scan keeps the floor", calls[-1].get("limit") == coordq.FLOOR,
      str(calls[-1].get("limit")))

# The explicit gate does not.
pr = {"number": 7, "head": {"sha": "a" * 40}, "body": f"Refs #9\nBuilder check: PASS {'a' * 40}\n"}
settings = {"key": "T", "projectId": "P"}
config = {"repos": {"o/r": settings}}
coordq.read_builder_thread = lambda thread_id: ({"providerInstanceId": "minimax",
                                                "model": "minimax/MiniMax-M3.1-Flash"},
                                               [{"executedModel": "minimax/MiniMax-M3.1-Flash"}])
coordq.builder_thread_for_issue = lambda repo, issue: "builder-1"
calls.clear()
found = coordq.gate_request("o/r", pr, settings, config, {}, "me", optional=False)
check("an explicit gate asks for no floor",
      bool(calls) and all(call.get("limit") is None for call in calls),
      str([call.get("limit") for call in calls]))
check("the explicit gate still finds the request", found is not None)

print("PROOF", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
