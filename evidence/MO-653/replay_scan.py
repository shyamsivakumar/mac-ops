import collections, importlib.util, io, json, os, re, sys, tempfile, types
from contextlib import redirect_stderr, redirect_stdout
from importlib.machinery import SourceFileLoader
checkout, N, M = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
qdir = tempfile.mkdtemp(prefix="replay-")
os.environ["COORDQ_DIR"] = qdir
sys.path.insert(0, f"{checkout}/coordinator/bin")
loader = SourceFileLoader("cq", f"{checkout}/coordinator/bin/coordq")
cq = importlib.util.module_from_spec(importlib.util.spec_from_loader("cq", loader)); loader.exec_module(cq)
REPO = "o/r"
prs = [{"draft": False, "number": n, "head": {"sha": f"{n:040x}"}, "body": f"Refs #{n}\n", "changed_files": 1, "base": {"ref": "main"}} for n in range(1, N + M + 1)]
heads = {}
receipts = {}
for pr in prs:
    key = f"gate:{REPO}#{pr['number']}:{pr['head']['sha']}"
    retry = pr["number"] > N
    heads[key] = {"id": pr["number"], "retries": 0, "at": None, "givenUp": not retry}
    if retry:
        receipts[key] = f"gate-{pr['number']}"
json.dump({"next": 1, "items": [], "gatedHeads": heads}, open(f"{qdir}/queue.json", "w"))
reads = collections.Counter()
def classify(path):
    path = re.sub(r"[0-9a-f]{40}", "*", path.split("?")[0]); return re.sub(r"\d+", "*", path)
def fake_run(argv, **kw):
    ep = [w for w in argv if w.startswith(("repos/", "user"))] or ["user"]
    path = ep[0]
    reads[classify(path)] += 1
    if path == "user": out = "me"
    elif path.startswith("repos/o/r/pulls?"): out = json.dumps([prs])
    elif "/issues/" in path: out = json.dumps([[{"user": {"login": "someone"}, "body": ""}]])
    elif "/statuses" in path: out = json.dumps([[]])
    else: out = json.dumps([[]])
    return types.SimpleNamespace(stdout=out, stderr="", returncode=0)
cq.gh_gateway.run = fake_run
cq.load_receipts = lambda: receipts
cq.read_builder_thread = lambda t: ({}, [])
cq.call = lambda tool, args, rules=None: (0, json.dumps({"thread": {"status": "running"}, "items": []}))
cfg = f"{qdir}/c.json"; json.dump({"repos": {REPO: {"key": "T", "projectId": "P"}}}, open(cfg, "w"))
with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
    cq.cmd_gatekeep(types.SimpleNamespace(config=cfg, dry_run=True))
print(f"gated heads never retryable: {N}; gated heads that may retry: {M}")
for k, v in sorted(reads.items()): print(f"  {v:4d}  {k}")
print(f"  total gh reads: {sum(reads.values())}")
