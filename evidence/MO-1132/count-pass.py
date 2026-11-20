import json, os, collections
from importlib.machinery import SourceFileLoader
import importlib.util
from unittest.mock import patch

LOG = os.path.expanduser("~/Library/Logs/coordinator/gh-usage.jsonl")

def rows():
    return [json.loads(l) for l in open(LOG) if l.strip()]

loader = SourceFileLoader("cq_count", "coordinator/bin/coordq")
spec = importlib.util.spec_from_loader(loader.name, loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)

before = len(rows())
with patch.object(m, "live_lane_repositories", return_value=set()), \
     patch.object(m, "log", side_effect=lambda line: print("LOG", line)):
    candidates = m.board_candidates()
after = [r for r in rows()[before:] if r.get("caller") == "count-pass.py"]
print("candidates", [(c["repository"]["nameWithOwner"], c["number"]) for c in candidates])
print("new usage rows", len(after))
print("by route", collections.Counter(r.get("route") for r in after))
print("paid", sum(1 for r in after if r.get("cost") != 0), "free", sum(1 for r in after if r.get("cost") == 0))
print("distinct calls", len({r.get("call") for r in after}))
