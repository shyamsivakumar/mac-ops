import sys, time, datetime
from unittest.mock import patch
sys.path.insert(0, "coordinator/overnight"); sys.path.insert(0, "coordinator/bin")
import lane_driver as lane
iso = lambda secs: datetime.datetime.fromtimestamp(time.time() - secs, datetime.timezone.utc).isoformat().replace("+00:00", "Z")
mk = lambda i, age, **kw: {"threadId": i, "title": kw.pop("title", "t"), "updatedAt": iso(age), "pinned": False, "blockedOnThreadWait": False, "pendingBackgroundTasks": [], **kw}
threads = [mk("recent", 300), mk("idle", 1200), mk("pinned", 1200, pinned=True), mk("ascend", 1200, title="Ascend x"), mk("old", 7200)]
calls = []
def fake(tool, args):
    if tool == "t3_thread_list":
        return {"threads": threads, "nextCursor": None}
    calls.append(args["threadId"]); return {"sequence": 1}
with patch.object(lane, "t3", fake):
    lane.settle_idle_completed({})
print("settled:", calls)
assert calls == ["idle"], calls
print("PASS")
