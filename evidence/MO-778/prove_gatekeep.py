"""Proof for #778: cmd_gatekeep queues 3 voters in the vote3 arm and 1 outside it.

Runs the real cmd_gatekeep with a fake candidate generator, a temp COORDQ_DIR
and a temp COORD_JOURNAL_DIR. Nothing touches the live queue, GitHub or t3.
"""

import argparse
import importlib.util
import json
import os
import sys
import tempfile
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ["COORDQ_DIR"] = tempfile.mkdtemp(prefix="mo778-queue-")
os.environ["COORD_JOURNAL_DIR"] = tempfile.mkdtemp(prefix="mo778-journal-")
sys.path.insert(0, str(ROOT / "coordinator" / "bin"))

loader = SourceFileLoader("coordq_mo778", str(ROOT / "coordinator" / "bin" / "coordq"))
coordq = importlib.util.module_from_spec(
    importlib.util.spec_from_loader("coordq_mo778", loader)
)
loader.exec_module(coordq)
import gate_vote
import journal

REPO, HEAD = "o/r", "a" * 40
CONFIG = Path(os.environ["COORDQ_DIR"]) / "config.json"
CONFIG.write_text(json.dumps({"repos": {REPO: {"key": "T", "projectId": "P"}}}))
MODEL = {"instanceId": "claudeAgent", "model": "claude-sonnet-5-5"}
EXPERIMENTS = [{"name": "gate-vote", "side": "gate", "split": 50, "names": ["vote3"]}]


def run(arm, dry):
    number = 1 if arm == "treatment" else 2
    key = f"gate:{REPO}#{number}:{HEAD}"
    args = coordq.gate_args(
        {"key": "T", "projectId": "P"},
        REPO,
        778,
        number,
        HEAD,
        False,
        MODEL,
        base="main",
    )
    event = {
        "kind": "gate",
        "pr": f"{REPO}#{number}",
        "head": HEAD,
        "key": key,
        "args": args,
        "scopeIssue": None,
        "builderModels": [],
    }
    coordq.gate_candidates = lambda *_, **_kw: iter([event])
    coordq.gh_gateway.remaining_or_none = lambda: None
    coordq.write_counts = lambda *_: None
    journal.factory_experiments = lambda: EXPERIMENTS
    journal.assigned_arm = lambda *_, **_kw: arm
    coordq.cmd_gatekeep(argparse.Namespace(config=str(CONFIG), dry_run=dry))
    return key


print("== dry run, arm treatment (vote3)")
run("treatment", True)
print("queue items after dry run:", len(coordq.load()["items"]))
print("== dry run, arm control")
run("control", True)
print("queue items after dry run:", len(coordq.load()["items"]))
print("== temp-queue run, arm treatment")
key = run("treatment", False)
print("== temp-queue run, arm control")
run("control", False)
queue = coordq.load()
for item in queue["items"]:
    print(
        item["id"],
        item["args"]["clientRequestId"],
        "|",
        item["title"],
        "| arm",
        item.get("arm"),
    )
heads = queue["gatedHeads"]
print("gatedHeads keys:", sorted(heads))
messages = [i["args"]["message"] for i in queue["items"][:3]]
bar_order = [
    [m.index(s) for s in ("Merge bar", "Severity bar", "Convergence rule")]
    for m in messages
]
print(
    "bar section order per voter:",
    [sorted(range(3), key=lambda i: o[i]) for o in bar_order],
)
print(
    "json ask in every voter:", all("Machine-readable verdict" in m for m in messages)
)
print(
    "lane sees voter threads for:",
    gate_vote.vote_threads(
        {f"vote:{key[5:]}:2": "T2", f"vote:{key[5:]}:3": "T3", key: "T1"}, key
    ),
)
