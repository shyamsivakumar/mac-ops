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

sys.path.insert(0, "scripts")
import mcp_reaper
start = int(time.time()) - 600
procs = {
    1: {"ppid": 0, "start": start - 900, "command": "/x/bin/codex app-server -c thread_unload_delay_secs=0"},
    11: {"ppid": 1, "start": start, "command": "/Applications/Paper.app/x/paper mcp"},
    12: {"ppid": 1, "start": start, "command": "/Applications/ChatGPT.app/x/cua_node/bin/node_repl"},
}
threads = [{"id": "resumed-live", "first": start - 900, "last": start + 500, "exited": False},
           {"id": "new-exited", "first": start + 1, "last": start + 30, "exited": True}]
signals = []
with patch.object(mcp_reaper, "snapshot", return_value=procs), patch.object(mcp_reaper, "host_threads", return_value=threads), \
        patch("subprocess.run", side_effect=lambda *a, **k: signals.append(a)), patch.object(sys, "argv", ["mcp_reaper"]):
    assert mcp_reaper.main() == 0
assert signals == [], signals
print("PASS reaper: resumed thread's set overlapping an exited new thread is reported, nothing signalled")
