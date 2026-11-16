#!/usr/bin/env python3
"""Prove that a legacy action key reports the state of its item.

The queue kept the state of an action key with the item that took it
only from the second cut of the key. A key written before that is a bare
item id, and the old reading of it said "dispatched" for every one of
them, so an item that was still waiting in the queue reported itself as
already sent. A key that is held also has to keep its state when the
queue writes it back.

The proof runs the real CLI against a temp queue with a stub t3mcp, so
the live queue is never read and never written. The queue file is made
by the CLI itself, so the shape of the queue is the real one.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COORDQ = ROOT / "coordinator" / "bin" / "coordq"

KEY = "rebase:shyamsivakumar/mac-ops#1:abc123"
PAYLOAD = json.dumps({"threadId": "mcp:launch:one",
                       "message": "PR #1 at abc needs rebase: conflict."})

STUB = '''#!/usr/bin/env python3
import json, os, sys
tool = sys.argv[2]
sys.stdin.read()
if tool == "t3_thread_list":
    print(json.dumps({"total": int(os.environ.get("STUB_LIVE", "0")),
                      "threads": [], "nextCursor": None}))
else:
    print(json.dumps({"ok": True, "tool": tool}))
'''

FAILURES = []


def check(name, condition, detail=""):
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f": {detail}" if detail else ""),
          flush=True)
    if not condition:
        FAILURES.append(name)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="coordq-legacy-key-"))
    queue_dir = tmp / "queue"
    queue_dir.mkdir()
    (queue_dir / "config.json").write_text(json.dumps({"cap": 6}))
    stub = tmp / "t3mcp"
    stub.write_text(STUB)
    stub.chmod(0o755)

    def env(live):
        return {**os.environ, "COORDQ_DIR": str(queue_dir),
                "COORDQ_T3MCP": str(stub), "STUB_LIVE": str(live),
                "PYTHONDONTWRITEBYTECODE": "1"}

    def run(args, live=6):
        return subprocess.run([sys.executable, str(COORDQ), *args],
                              env=env(live), capture_output=True, text=True)

    def queue_state():
        return json.loads((queue_dir / "queue.json").read_text())

    def write_queue(state):
        (queue_dir / "queue.json").write_text(json.dumps(state))

    # 1. The queue takes the key, so the queue file is the real shape.
    result = run(["start", PAYLOAD, "--tool", "t3_thread_send",
                  "--priority", "800", "--action-key", KEY])
    check("the key is taken by a queued item",
          result.returncode == 0 and result.stdout.strip() == "queued #1",
          f"rc={result.returncode} out={result.stdout.strip()!r}")

    # 2. The same key written the old way, as a bare item id, is read
    #    from the queue: the item is still queued, so it is not dispatched.
    state = queue_state()
    state["actionKeys"] = {KEY: state["items"][0]["id"]}
    write_queue(state)
    result = run(["start", PAYLOAD, "--tool", "t3_thread_send",
                  "--priority", "800", "--action-key", KEY])
    check("a legacy key of a queued item is refused",
          result.returncode == 1, f"rc={result.returncode}")
    check("the refusal says queued, not dispatched",
          "already queued" in result.stderr and "dispatched" not in result.stderr,
          result.stderr.strip())

    # 3. A legacy key of an item that is nowhere in the queue says
    #    "dispatched", so the same board action is never sent twice.
    state = queue_state()
    state["actionKeys"] = {KEY: 7}
    write_queue(state)
    result = run(["start", PAYLOAD, "--tool", "t3_thread_send",
                  "--priority", "800", "--action-key", KEY])
    check("a legacy key of a gone item is refused",
          result.returncode == 1, f"rc={result.returncode}")
    check("the refusal says dispatched and names the item",
          "already dispatched" in result.stderr and "#7" in result.stderr,
          result.stderr.strip())

    # 4. The queue writes the state of a legacy key back into the map,
    #    so the key keeps its state from now on.
    state = queue_state()
    state["actionKeys"] = {KEY: state["items"][0]["id"]}
    write_queue(state)
    result = run(["dispatch"], live=0)
    state = queue_state()
    check("the dispatched legacy key keeps its state",
          state.get("actionKeys") == {KEY: {"id": 1, "state": "dispatched"}},
          json.dumps(state.get("actionKeys")))
    result = run(["start", PAYLOAD, "--tool", "t3_thread_send",
                  "--priority", "800", "--action-key", KEY])
    check("the dispatched legacy key is refused",
          result.returncode == 1 and "already dispatched" in result.stderr,
          result.stderr.strip())

    # 5. A record the queue cannot read keeps its key held.
    state = queue_state()
    state["actionKeys"] = {KEY: {"state": "queued"}}
    write_queue(state)
    result = run(["start", PAYLOAD, "--tool", "t3_thread_send",
                  "--priority", "800", "--action-key", KEY])
    check("a record without an item id stays held",
          result.returncode == 1 and KEY in result.stderr,
          result.stderr.strip())

    print(f"rig: {tmp}", flush=True)
    if FAILURES:
        print(f"FAIL {len(FAILURES)} check(s): {', '.join(FAILURES)}", flush=True)
        return 1
    print("PASS every check", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
