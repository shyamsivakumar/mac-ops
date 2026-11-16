#!/usr/bin/env python3
"""Prove that the board's printed actionCommand runs as printed.

The board prints one command per action it wants, and the command carries
the key of that action. The proof runs the real CLI against a temp queue
and a stub t3mcp, so the live queue is never read and never written.

The command is the one the board printed right now: the proof reads the
board, takes the first item that carries an action, and runs that string
as a shell would run it. When the board has no action to print, the proof
falls back to the item the board printed on 2026-11-16 at 10:06 PT (LMW
#213 was CONFLICTING at 025b02c9 and the board sent the command to the
builder thread of its ticket), whose head and thread come from the
coordinator's own records.
"""

import json
import os
import shlex
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "coordinator" / "overnight" / "overnight"
COORDQ = ROOT / "coordinator" / "bin" / "coordq"

REPO = "shyamsivakumar/sams-llm-wiki"
NUMBER = 213
HEAD = "025b02c9ed290dbb453dc082c5e83969034aa5ad"
ACTION = "rebase"
STATE = "conflict"
TARGET = "mcp:launch:ea8e8c68c7fbe81ae3876f1ba998088ebe0dd7175a09e03df26981f490c2d07f"

STUB = '''#!/usr/bin/env python3
import json, os, sys
tool = sys.argv[2]
payload = sys.stdin.read()
try:
    args = json.loads(payload or "{}")
except ValueError:
    args = {"raw": payload}
with open(os.environ["STUB_LOG"], "a") as f:
    f.write(json.dumps({"tool": tool, "args": args}) + "\\n")
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


def board_command():
    """The command the board prints for a real item.

    The live board is read first, so the proof runs the string the board
    writes right now. The fallback is the board's own three source lines
    run with the values of the item the board printed on 2026-11-16."""
    board = subprocess.run([sys.executable, str(BOARD), "board", "--json", "--action"],
                           capture_output=True, text=True, timeout=180, cwd=str(ROOT))
    if board.returncode == 0:
        try:
            items = json.loads(board.stdout)["items"]
        except ValueError:
            items = []
        for item in items:
            if item.get("actionCommand"):
                command = item["actionCommand"]
                print(f"live board item: {item['repo']}#{item['number']} "
                      f"at {item.get('head')} action {item.get('action')}", flush=True)
                return command, json.loads(shlex.split(command)[2])
    print("the live board carries no action: the recorded item of "
          "2026-11-16 10:06 PT is used instead", flush=True)
    lines = BOARD.read_text().splitlines()
    start = next(index for index, line in enumerate(lines)
                 if 'payload = {"threadId": target' in line)
    block = textwrap.dedent("\n".join(lines[start:start + 3]))
    scope = {"json": json, "shlex": shlex, "action": ACTION, "repo": REPO,
             "number": NUMBER, "item": {"head": HEAD}, "target": TARGET,
             "state": STATE}
    exec(block, scope)
    return scope["item"]["actionCommand"], scope["payload"]


def main():
    command, payload = board_command()
    print(f"board actionCommand: {command}", flush=True)

    tmp = Path(tempfile.mkdtemp(prefix="coordq-action-key-"))
    queue_dir = tmp / "queue"
    home = tmp / "home"
    queue_dir.mkdir()
    home.mkdir()
    (queue_dir / "config.json").write_text(json.dumps({"cap": 6}))
    (home / ".coordinator").mkdir()
    (home / ".coordinator" / "AGENT-RULES.md").write_text("rules\n")
    (home / ".coordinator" / "tickets.json").write_text(json.dumps({"repos": {}}))
    stub = tmp / "t3mcp"
    stub.write_text(STUB)
    stub.chmod(0o755)
    log = tmp / "calls.log"
    log.write_text("")

    def env(live):
        return {**os.environ, "COORDQ_DIR": str(queue_dir),
                "COORDQ_T3MCP": str(stub), "HOME": str(home),
                "COORDQ_RULES": str(home / ".coordinator" / "AGENT-RULES.md"),
                "STUB_LOG": str(log), "STUB_LIVE": str(live),
                "PYTHONDONTWRITEBYTECODE": "1"}

    def run(args, live=6, binary=COORDQ):
        return subprocess.run([sys.executable, str(binary), *args],
                              env=env(live), capture_output=True, text=True)

    def queue_state():
        return json.loads((queue_dir / "queue.json").read_text())

    # 1. The command as printed, with the flag, enqueues without an edit.
    # The command is split the way a shell splits it, so the key arrives
    # as the board wrote it.
    argv = shlex.split(command)
    key = argv[-1]
    args = argv[1:]
    print(f"board action key:     {key}", flush=True)
    result = run(args)
    check("the printed command enqueues", result.returncode == 0
          and result.stdout.strip() == "queued #1",
          f"rc={result.returncode} out={result.stdout.strip()!r} err={result.stderr.strip()!r}")
    state = queue_state()
    check("the key is on the queued item",
          state["items"][0].get("actionKey") == key, json.dumps(state["items"][0]))
    check("the queued item carries the payload the board printed",
          state["items"][0]["args"] == payload)
    check("the queue holds the key", state.get("actionKeys") == {key: 1},
          json.dumps(state.get("actionKeys")))

    # 2. The same command a second time is refused, and nothing changes.
    before = queue_state()
    cap_before = json.loads((queue_dir / "config.json").read_text())["cap"]
    result = run(args)
    after = queue_state()
    check("the second run is refused", result.returncode != 0
          and key in result.stderr and "#1" in result.stderr,
          f"rc={result.returncode} err={result.stderr.strip()!r}")
    check("the refusal is a duplicate key line", "already" in result.stderr,
          result.stderr.strip())
    check("the queue is unchanged", after["items"] == before["items"]
          and after["next"] == before["next"]
          and after.get("actionKeys") == before.get("actionKeys"))
    check("the cap is untouched",
          json.loads((queue_dir / "config.json").read_text())["cap"] == cap_before)

    # 3. The help names the flag, and a start without it still enqueues.
    result = run(["start", "--help"])
    check("the help lists --action-key", "--action-key" in result.stdout)
    result = run(["start", json.dumps(payload), "--tool", "t3_thread_send",
                  "--priority", "800"])
    check("a start without the flag enqueues", result.returncode == 0
          and result.stdout.strip() == "queued #2",
          f"rc={result.returncode} out={result.stdout.strip()!r} err={result.stderr.strip()!r}")
    state = queue_state()
    check("the item without the flag carries no key",
          "actionKey" not in state["items"][1])

    # 4. The dispatch log carries the key next to the item it started.
    result = run(["dispatch"], live=0)
    dispatch_log = (queue_dir / "dispatch.log").read_text()
    started = [line for line in dispatch_log.splitlines() if " started #1 " in line]
    check("the started line names the key", bool(started) and f"key {key}" in started[0],
          started[0] if started else dispatch_log)

    # The binary before this change refuses the flag the board prints.
    old = tmp / "coordq-old"
    base = subprocess.run(["git", "-C", str(ROOT), "merge-base", "origin/main", "HEAD"],
                           capture_output=True, text=True, check=True).stdout.strip()
    old.write_bytes(subprocess.run(["git", "-C", str(ROOT), "show",
                                    f"{base}:coordinator/bin/coordq"],
                                   capture_output=True, check=True).stdout)
    for name in ("gate_bar.py", "tick_health.py"):
        (tmp / name).write_bytes((ROOT / "coordinator" / "bin" / name).read_bytes())
    result = run(args, binary=old)
    check("the binary before this change refused the flag",
          result.returncode != 0 and "unrecognized arguments" in result.stderr,
          f"rc={result.returncode} err={result.stderr.strip()[:160]}")

    print(f"rig: {tmp}", flush=True)
    if FAILURES:
        print(f"FAIL {len(FAILURES)} check(s): {', '.join(FAILURES)}", flush=True)
        return 1
    print("PASS every check", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
