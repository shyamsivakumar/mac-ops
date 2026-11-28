import json
import os
import subprocess
import sys
import time

POLL_SECONDS = 40
BATCH_SECONDS = 180
SWEEP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "board_sweep.py")


def threads():
    out = (
        subprocess.run(
            [
                "emp",
                "call",
                "emp_thread_list",
                json.dumps({"allProjects": True, "limit": 100}),
            ],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        or "{}"
    )
    try:
        data = json.loads(out, strict=False)
    except json.JSONDecodeError as e:
        print(f"bad emp_thread_list reply: {e}", file=sys.stderr)
        return None
    return next((v for v in data.values() if isinstance(v, list)), [])


def pending(t):
    return (t.get("pendingRequestCount") or 0) > 0 or t["status"] == "waiting"


subprocess.run([sys.executable, SWEEP, "--act", "--json-only"], check=False)
first = threads() or []
seen = {t["threadId"]: (t["status"], t.get("updatedAt")) for t in first}
already_pending = {t["threadId"] for t in first if pending(t)}
events, first_at = [], None

while True:
    time.sleep(POLL_SECONDS)
    finished = False
    polled = threads()
    if polled is None:
        continue
    for t in polled:
        key, status, updated = t["threadId"], t["status"], t.get("updatedAt")
        if str(t.get("title", "")).startswith("PRF-"):
            continue
        if pending(t) and key not in already_pending:
            events.append(f"PENDING {key} {status} {t['title']}")
            already_pending.add(key)
        elif (
            status in ("completed", "failed")
            and seen.get(key, (None, None))[1] != updated
        ):
            events.append(f"DONE {key} {status} {t['title']}")
            finished = True
        seen[key] = (status, updated)
    if finished:
        subprocess.run([sys.executable, SWEEP, "--act", "--json-only"], check=False)
    if events and first_at is None:
        first_at = time.time()
    if first_at is not None and time.time() - first_at >= BATCH_SECONDS:
        print("\n".join(events))
        sys.exit(0)
