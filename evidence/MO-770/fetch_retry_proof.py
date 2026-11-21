"""Gatekeep fetch retry proof: a fetch that fails once then works gates green on tick 2; a fetch that always fails gives one card after 3 ticks and no more attempts."""
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
bodies = {1: "Proof command:\ntest -f README.md\n", 2: "Proof command:\ntest -f README.md\n"}
loader = importlib.machinery.SourceFileLoader("coordq", "coordinator/bin/coordq")
q = importlib.util.module_from_spec(importlib.util.spec_from_loader("coordq", loader))
loader.exec_module(q)
q.gh_json = lambda ep, **k: {"body": bodies[int(ep.rsplit("/", 1)[1])]}
q.gh_gateway.remaining_or_none = lambda: None
q.lane_ledger = lambda: {}
model = {"instanceId": "i", "model": "m"}
for opened in (1, 2):
    q.journal.emit("ticket_opened", "ticket", repo="o/on", ticket=opened, proof="red")
fetches = {1: 0, 2: 0}
real_run = subprocess.run


def flaky(cmd, *a, **k):
    if isinstance(cmd, list) and "fetch" in cmd and cmd[-1].startswith("refs/pull/"):
        pr = int(cmd[-1].split("/")[2])
        fetches[pr] += 1
        if pr == 2 or fetches[pr] == 1:
            return types.SimpleNamespace(returncode=128, stdout="", stderr="fatal: unable to access github.com")
    return real_run(cmd, *a, **k)


subprocess.run = flaky


def candidates(config, rounds=None):
    for pr in (1, 2):
        key = f"gate:o/on#{pr}:{heads[pr]}"
        yield {"kind": "candidate", "pr": f"o/on#{pr}", "head": heads[pr], "key": key, "issue": pr,
               "size": "whole", "args": {"title": f"t{pr}", "message": "brief", "modelSelection": model,
                                         "clientRequestId": key}}
q.gate_candidates = candidates
cfg = root + "/cfg.json"
json.dump({"repos": {"o/on": {"key": "MO", "proofOnOpen": True, "checkout": work}}}, open(cfg, "w"))
args = types.SimpleNamespace(config=cfg, dry_run=False)
for tick in range(1, 6):
    q.cmd_gatekeep(args)
    queue = q.load()
    print(f"tick {tick}: fetch attempts {fetches} | queued {[i['title'] for i in queue['items']]} | "
          f"proofHeads { {k.split(':')[1]: v['state'] for k, v in queue.get('proofHeads', {}).items()} } | "
          f"cards {[i['id'] for i in json.load(open(root + '/mac-ops-owner.json'))['items']] if os.path.exists(root + '/mac-ops-owner.json') else []}")
print("proofFetch:", {k.split(":")[1]: (v["attempts"], v["error"][:40]) for k, v in q.load()["proofFetch"].items()})
