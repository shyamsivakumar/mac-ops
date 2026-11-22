import sys, os, json, tempfile
from unittest.mock import patch
sys.path[:0] = ["coordinator/bin", "coordinator/overnight"]
tmp = tempfile.mkdtemp()
os.environ["COORDQ_DIR"] = tmp + "/q"; os.environ["COORD_JOURNAL_DIR"] = tmp + "/j"; os.environ["HOME"] = tmp
import lane_driver as L
board = tmp + "/decisions.json"
L.DECISIONS_PATH = board
L.CFG = {"shyamsivakumar/mac-ops": {"key": "MO", "projectId": "fixture"}}
repo, head = "shyamsivakumar/mac-ops", "a" * 40
raised = []
def cards():
    return list(raised)
real = L.publish_decision
def spy(item):
    raised.append(item["id"])
    return real(item)
L.publish_decision = spy
def run(number, paths, labels, ledger):
    merges = []
    pr = {"changedFiles": len(paths), "baseRefName": "main", "labels": [{"name": n} for n in labels]}
    gate = {"threadId": "t"}
    with patch.object(L, "prompt_pull", lambda *a, **k: L.prompt_paths.prompt_scan(paths)), \
         patch.object(L, "clear_gate_round_decision", lambda *a: True), \
         patch.object(L, "merge_mode", lambda *a: "auto"), \
         patch.object(L, "merge_on_reviewed_base", lambda *a: (merges.append(a) or (False, "merge call reached"))), \
         patch.object(L, "journal_event", lambda *a, **k: print("   journal:", a[0], k.get("reason"))):
        out = L.merge_passed_pr(repo, number, head, pr, {}, gate, ledger)
    print(f"#{number} {paths} labels={labels}\n   -> {out}\n   merge calls={len(merges)} cards={cards()}")
led = {}
run(1, ["coordinator/bin/coordq"], [], led)
run(1, ["coordinator/bin/coordq"], [], led)
run(1, ["coordinator/bin/coordq"], ["merge:human-ok"], led)
run(2, ["README.md"], [], {})
run(3, ["skills/x/SKILL.md", "coordinator/bin/coordq"], ["merge:human-ok"], {})
import glob
for f in glob.glob(tmp + "/**/*.json", recursive=True):
    try:
        d = json.load(open(f))
    except ValueError:
        continue
    if isinstance(d, dict) and "items" in d:
        print("board", os.path.basename(f), [i["id"] for i in d["items"]])
