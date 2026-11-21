"""Gatekeep proof: green head gated with the record, red head carded once, flag off unchanged."""
import sys; sys.path.insert(0, "coordinator/bin")
import importlib.machinery, importlib.util, json, os, subprocess, sys, tempfile, types

root = tempfile.mkdtemp(prefix="gk770-")
for name in ("queue", "journal", "home"):
    os.makedirs(os.path.join(root, name))
os.environ.update(COORDQ_DIR=root + "/queue", COORD_JOURNAL_DIR=root + "/journal", HOME=root + "/home",
                  COORDINATOR_DECISIONS=root + "/decisions.json")
sh = lambda *a, cwd=None: subprocess.run(a, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()
origin, work = root + "/origin.git", root + "/work"
sh("git", "init", "--bare", "-b", "main", origin)
sh("git", "clone", origin, work)
for k, v in (("user.email", "a@b"), ("user.name", "t")):
    sh("git", "config", k, v, cwd=work)
open(work + "/README.md", "w").write("x\n")
sh("git", "add", ".", cwd=work), sh("git", "commit", "-m", "base", cwd=work), sh("git", "push", "origin", "HEAD:main", cwd=work)
heads = {}
for pr in (1, 2):
    sh("git", "checkout", "-q", "-b", f"b{pr}", "main", cwd=work)
    open(work + f"/f{pr}", "w").write("y\n")
    sh("git", "add", ".", cwd=work), sh("git", "commit", "-m", f"pr{pr}", cwd=work)
    heads[pr] = sh("git", "rev-parse", "HEAD", cwd=work)
    sh("git", "push", "origin", f"HEAD:refs/pull/{pr}/head", cwd=work)
bodies = {1: "Proof command:\ntest -f README.md\n", 2: "Proof command:\ntest -f MISSING\n", 3: "Proof command:\ntest -f MISSING\n"}

loader = importlib.machinery.SourceFileLoader("coordq", "coordinator/bin/coordq")
q = importlib.util.module_from_spec(importlib.util.spec_from_loader("coordq", loader))
loader.exec_module(q)
q.gh_json = lambda ep, **k: {"body": bodies[int(ep.rsplit("/", 1)[1])]}
q.gh_gateway.remaining_or_none = lambda: None
q.lane_ledger = lambda: {}
model = {"instanceId": "i", "model": "m"}
runs = []
import proof_run
real_run = proof_run.run
proof_run.run = lambda *a, **k: (runs.append(a[2]), real_run(*a, **k))[1]


def candidates(config, rounds=None):
    for pr, repo in ((1, "o/on"), (2, "o/on"), (3, "o/off")):
        h = heads.get(pr, "c" * 40)
        key = f"gate:{repo}#{pr}:{h}"
        yield {"kind": "candidate", "pr": f"{repo}#{pr}", "head": h, "key": key, "issue": pr,
               "size": "whole", "args": {"title": f"t{pr}", "message": "brief", "modelSelection": model,
                                         "clientRequestId": key}}
q.gate_candidates = candidates
cfg = root + "/cfg.json"
json.dump({"repos": {"o/on": {"key": "MO", "proofOnOpen": True, "checkout": work},
                     "o/off": {"key": "OFF"}}}, open(cfg, "w"))
args = types.SimpleNamespace(config=cfg, dry_run=False)
for round_no in (1, 2):
    q.cmd_gatekeep(args)
    print(f"--- run {round_no}: proof runs so far {len(runs)}")
queue = q.load()
for item in queue["items"]:
    print("queued", item["title"], "| proof in brief:", "Proof run by Gatekeep" in item["args"]["message"])
print("card:", [i["id"] for i in json.load(open(root + "/mac-ops-owner.json"))["items"]])
print("replay:", sorted(os.listdir(root + "/replay/MO-1")))
print("proof_run rows:", [l.strip()[-90:] for f in os.listdir(root + "/journal")
                          for l in open(root + "/journal/" + f) if '"proof_run"' in l])
print("proofHeads:", {k.split(":")[1]: v["state"] for k, v in queue["proofHeads"].items()})
