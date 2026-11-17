#!/usr/bin/env python3
"""MO-1057: the whole tick finishes under 600 seconds when a call hangs.

The tick is the launcher in `coordinator/pi/bin/coord-tick`. This proof runs
that launcher for real. One of its GitHub calls is pointed at a blackhole
address of this machine's own: a listening socket that accepts the
connection and never answers, so the call hangs the way the call of
2026-11-17 hung (a connect that never completes, with no client timeout).
The agent turn is stood in for by a script that reads the board, does the
rest of its work and replies.

    /opt/homebrew/bin/python3 evidence/MO-1057/proof.py
"""
import importlib.util
import os
import re
import socket
import sys
import tempfile
import threading
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TICK = ROOT / "coordinator" / "pi" / "bin" / "coord-tick"
OVERNIGHT = ROOT / "coordinator" / "overnight" / "overnight"
PYTHON = "/opt/homebrew/bin/python3"

BLACKHOLE_GH = """#!/bin/sh
# A GitHub call pointed at a blackhole: the port accepts and never answers,
# so the call waits with no client timeout of its own.
exec /usr/bin/curl -sS --connect-timeout 600 --max-time 600 \\
  http://127.0.0.1:{port}/github
"""

AGENT_TURN = """#!/bin/sh
# The stand-in for the tick's agent turn.
if [ "$1" = "--list-models" ]; then
  echo "deepseek/deepseek-flash"
  exit 0
fi
{board} > "$TICK_PROOF_DIR/board.out" 2> "$TICK_PROOF_DIR/board.err"
skipped=$(grep -c '^overnight: skipped' "$TICK_PROOF_DIR/board.err")
# The rest of the tick still runs after the hung call: the checks of
# loop/tick.md that need no GitHub, read for real.
{other_work} > "$TICK_PROOF_DIR/other-work.txt"
lanes=$(grep '^lanes: ' "$TICK_PROOF_DIR/other-work.txt")
if [ "$skipped" -gt 0 ]; then
  echo "NOOP the board read skipped $skipped calls; the other checks ran: $lanes"
else
  echo "NOOP the board read was not skipped; the other checks ran: $lanes"
fi
"""


def load(path, name):
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def blackhole() -> tuple[socket.socket, int, threading.Event]:
    """A listener that accepts a connection and never answers.

    The kernel completes the handshake from the backlog, so the client's
    connect succeeds and its read never returns: a hang with no answer,
    which is the shape of the call that cost the tick of 2026-11-17 its
    ten minutes."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    # Enough of a backlog for every repository's call to sit unanswered.
    server.listen(128)
    stop = threading.Event()

    def hold() -> None:
        # The connections are never accepted and never answered, so the
        # callers wait until their own timeout ends.
        while not stop.is_set():
            time.sleep(0.2)

    threading.Thread(target=hold, daemon=True).start()
    return server, server.getsockname()[1], stop


def main() -> int:
    tick = load(TICK, "coord_tick_proof")
    server, port, stop = blackhole()
    try:
        with tempfile.TemporaryDirectory() as scratch:
            home = Path(scratch)
            # The blackhole call is only the one the board read makes: it
            # is named by OVERNIGHT_GH and it is not on PATH, so the
            # ticket CLI still reaches the real GitHub.
            blackhole_dir = home / "blackhole"
            blackhole_dir.mkdir()
            gh = blackhole_dir / "gh"
            gh.write_text(BLACKHOLE_GH.format(port=port))
            gh.chmod(0o755)
            agent = home / "pi"
            agent.write_text(
                AGENT_TURN.format(
                    board=f"{PYTHON} {OVERNIGHT} board --json --action",
                    other_work=f"{PYTHON} {ROOT / 'evidence/MO-1057/other_work.py'}",
                )
            )
            agent.chmod(0o755)
            log = home / "tick.log"
            os.environ["COORD_TICK_LOG"] = str(log)
            os.environ["COORD_TICK_LOCK"] = str(home / "coord-tick.lock")
            os.environ["TICK_PROOF_DIR"] = str(home)
            os.environ["OVERNIGHT_GH"] = str(gh)
            # The stand-in for the agent turn is found first, and the
            # selftest is not due, the way the killed tick found it.
            tick.CHILD_PATH = f"{scratch}:{tick.CHILD_PATH}"
            tick.LOG_PATH = log
            tick.tick_selftest = lambda: "not-due"
            tick.tick_alarm = lambda: ""
            started = time.monotonic()
            code = tick.main()
            elapsed = time.monotonic() - started
            print(f"tick exit={code} elapsed={elapsed:.0f}s")
            print("--- the tick log")
            print(log.read_text().rstrip())
            print("--- the calls the tick skipped")
            skips = [
                line
                for line in (home / "board.err").read_text().splitlines()
                if line.startswith("overnight: skipped")
            ]
            for line in skips[:3]:
                print(line)
            print(f"--- skipped calls: {len(skips)}")
            print("--- the rest of the tick's work, read for real")
            other = (home / "other-work.txt").read_text().rstrip()
            print(other)
            # The continuation is only proved when the other checks ran
            # and read real values: a measured age, a counted traceback
            # and the state of the launchd job.
            measured = [
                line
                for line in other.splitlines()
                if re.search(r"age \d+s", line)
                or re.search(r"traceback \d+", line)
                or line.startswith("launchd: ")
            ]
            ok = (
                elapsed < 600
                and code == 0
                and bool(skips)
                and len(measured) >= 4
            )
            print(f"--- the checks that ran after the hung call: {len(measured)}")
            print(f"--- the tick finished under 600 seconds: {ok}")
            return 0 if ok else 1
    finally:
        stop.set()
        server.close()


if __name__ == "__main__":
    sys.exit(main())
