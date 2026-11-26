import sys, os, json, tempfile, importlib.machinery, importlib.util
tmp = tempfile.mkdtemp()
os.environ.update(COORD_JOURNAL_DIR=tmp+"/j", COORDQ_DIR=tmp+"/q", HOME=tmp)
sys.path.insert(0, "coordinator/bin")
def load(name):
    l = importlib.machinery.SourceFileLoader(name, f"coordinator/bin/{name}")
    spec = importlib.util.spec_from_loader(name, l); m = importlib.util.module_from_spec(spec); l.exec_module(m); return m
import journal
ticket = load("ticket")

def issue(blockers):
    return {"blockedBy": {"totalCount": len(blockers), "nodes": [
        {"number": n, "title": "t", "url": f"https://github.com/o/r/issues/{n}", "state": "OPEN"} for n in blockers]}}
graph = {}
ticket.blocker_repo = lambda node: "o/r"
def fetch(repo, n):
    if n not in graph: raise ticket.GhError.__new__(ticket.GhError)
    return graph[n]
ticket.fetch_issue = fetch

graph.update({2: issue([1]), 1: issue([])})
print("chain", ticket.cluster_root("o/r", 3, issue([2])))
graph.clear(); graph.update({2: issue([3]), 3: issue([2])})
print("cycle", ticket.cluster_root("o/r", 3, issue([2])), ticket.cluster_root("o/r", 2, graph[2]))
graph.clear(); graph.update({n: issue([n+1]) for n in range(10, 30)})
print("depth", ticket.cluster_root("o/r", 9, issue([10])))
graph.clear()
print("unreadable", ticket.cluster_root("o/r", 9, issue([10])))
print("truncated", ticket.cluster_root("o/r", 9, {"blockedBy": {"totalCount": 3, "nodes": []}}))

print("no experiment stamp", ticket.cluster_stamp("o/r", 9, issue([10])))
journal.factory_experiments = lambda: [{"name": "x", "split": 50, "side": "builder"}, {"name": "g", "split": 50, "side": "gate"}]
graph.update({10: issue([])})
st = ticket.cluster_stamp("o/r", 9, issue([10])); print("experiment stamp", st)
journal.emit("assigned", "ticket", repo="o/r", ticket=9, attempt=1, **st)
sys.argv=["coordq"]; coordq = load("coordq")
coordq.journal_item("launched", {"id": 1, "tool": "t3_thread_launch", "args": {"clientRequestId": "ticket:o/r#9:a1"}, "title": "t"})
coordq.journal_item("launched", {"id": 2, "tool": "t3_thread_launch", "args": {"clientRequestId": "ticket:o/r#8:a1"}, "title": "t"})
for line in open(tmp+"/j/"+os.listdir(tmp+"/j")[0]):
    r = json.loads(line); print(r["event"], r["repo"], r["ticket"], "arm=", r["arm"], {k: v for k, v in r["data"].items() if k in ("cluster","cluster_note","gate_arm")})
print("gate arm", journal.assigned_arm("o/r", "9", gate=True), journal.assigned_arm("o/r", None, gate=True))

print("--- crash paths")
import importlib
home = tempfile.mkdtemp(); os.makedirs(home + "/.coordinator")
here_cfg = os.path.join(os.path.realpath("coordinator/bin"), "..", "config", "factory.json")
importlib.reload(journal)
real = journal.os.path.exists
journal.os.path.exists = lambda p: False if p == here_cfg else real(p)
os.environ["HOME"] = home
cfg = home + "/.coordinator/factory.json"
def reg(text):
    open(cfg, "w").write(text); journal._NOTED.clear(); return journal.factory_experiments()
print("malformed json", reg("{nope"))
print("not an object", reg("[1]"))
print("bad entries", reg(json.dumps({"experiments": [{"name": "a", "side": "other", "split": 5}, {"name": "b", "side": "gate"}, {"name": "c", "side": "gate", "split": "x"}, "junk"]})))
two = reg(json.dumps({"experiments": [{"name": "a", "side": "builder", "split": 10}, {"name": "b", "side": "builder", "split": 90}, {"name": "g", "side": "gate", "split": 50}]}))
print("one per side", [e["name"] for e in two])
j = os.environ["COORD_JOURNAL_DIR"]; os.makedirs(j, exist_ok=True)
open(j + "/events-2026-12.jsonl", "w").write('{"event":"assigned","repo":"o/r","ticket":7,"arm":"treatment"}\n5\nnot json\n')
os.makedirs(j + "/events-2026-09.jsonl", exist_ok=True)
open(j + "/events-2026-10.jsonl", "wb").write(b"\xff\xfe\n")
print("assigned row without data", journal.assigned_arm("o/r", 7), journal.assigned_arm("o/r", 7, gate=True))
print("non-numeric ticket", journal.assigned_arm("o/r", "abc"), journal.assigned_arm("o/r", None), journal.assigned_arm("o/r", 99))
