import contextlib, io, json, os, sys, tempfile
from unittest.mock import patch

tmp = tempfile.mkdtemp()
os.environ["COORD_JOURNAL_DIR"] = tmp
os.environ["COORDQ_DIR"] = tmp
sys.path[:0] = ["scripts", "coordinator/overnight", "coordinator/bin"]
import lane_driver as lane
import settle_finished

thread = lambda i, **kw: {"threadId": i, "title": kw.pop("title", "t"), "status": "completed", **kw}
threads = [
    thread("merged", pullRequests=[{"state": "merged", "repository": "o/r"}]),
    thread("open-pr", pullRequests=[{"state": "open", "repository": "o/r"}]),
    thread("closed-ticket"),
    thread("verdict"),
    thread("pinned", pinned=True, pullRequests=[{"state": "merged"}]),
    thread("ascend", title="Ascend fix", pullRequests=[{"state": "merged"}]),
    thread("plain"),
]
receipts = os.path.join(tmp, "receipts.json")
with open(receipts, "w") as handle:
    json.dump({"ticket:o/r#7": "closed-ticket"}, handle)
with open(os.path.join(tmp, "events-2026-11-27.jsonl"), "w") as handle:
    handle.write(json.dumps({"event": "gate_verdict", "thread": "verdict", "data": {"verdict": "PASS"}}) + "\nnot json\n")

organize = []
def fake_t3(tool, args):
    if tool == "t3_thread_list":
        return {"threads": threads, "nextCursor": None}
    if tool == "t3_project_list":
        return {"projects": []}
    organize.append(args)
    return {}

out = io.StringIO()
with patch.object(lane, "t3", fake_t3), patch.object(lane, "RECEIPTS", receipts), \
        patch.object(lane, "run", lambda cmd, timeout=150: json.dumps([{"number": 7}])), \
        patch.object(sys, "argv", ["settle_finished.py", "--dry-run"]), contextlib.redirect_stdout(out):
    code = settle_finished.main()
print(out.getvalue())
assert code == 0 and organize == [], (code, organize)
for line in ("settle:    1 pull request merged or closed", "settle:    1 ticket issue closed",
             "settle:    1 gate verdict recorded", "skip:      1 pinned", "skip:      1 Ascend or slash-eureka",
             "skip:      2 work not finished"):
    assert line in out.getvalue(), line
print("PASS")
