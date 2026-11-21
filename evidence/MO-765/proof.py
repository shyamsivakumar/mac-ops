import argparse, json, os, sys, tempfile
from pathlib import Path
root = Path(tempfile.mkdtemp())
(root / "q").mkdir(); (root / "j").mkdir()
os.environ.update(COORDQ_DIR=str(root / "q"), COORD_JOURNAL_DIR=str(root / "j"),
                  COORDINATOR_DECISIONS=str(root / "decisions.json"), HOME=str(root))
(root / "decisions.json").write_text(json.dumps({"items": []}))
sys.path.insert(0, str(Path.cwd()))
from tests.test_gatekeep_backstop_reviewer import load_coordq
q = load_coordq()
(root / "rules.md").write_text("rules")
q.RULES_PATH = str(root / "rules.md")
q.cap = lambda: 0
q.live = lambda: 99
q.gh_gateway.remaining_or_none = lambda: None
q.save({"next": 1, "items": []})
KEY = "gate:o/mac-ops#9:" + "a" * 40
def candidates(config, rounds=None):
    if KEY not in q.load().get("recutHeads", {}):
        yield {"kind": "candidate", "pr": "o/mac-ops#9", "head": "a" * 40, "key": KEY, "size": "recut",
               "lines": 800, "files": 4, "args": {}}
q.gate_candidates = candidates
config = root / "config.json"
config.write_text(json.dumps({"repos": {"o/mac-ops": {"key": "MO", "projectId": "p1"}}}))
def run():
    q.cmd_gatekeep(argparse.Namespace(config=str(config), dry_run=False))
    return [i["args"] for i in q.load()["items"]]
for label in ("run 1", "run 2 same head"):
    items = run()
    print(label, "briefs queued:", len(items))
b = items[0]
print("model:", b["modelSelection"], "taskType:", b["taskType"], "action keys:", list(q.load()["actionKeys"]) if "actionKeys" in q.load() else [k for k in q.load() if "ction" in k])
print(b["message"])
