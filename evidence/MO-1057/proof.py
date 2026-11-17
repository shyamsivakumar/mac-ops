#!/usr/bin/env python3
"""MO-1057: the whole tick finishes under 600 seconds when a call hangs.

The tick is the launcher in `coordinator/pi/bin/coord-tick`, and it runs the
real agent: the real `pi`, the real coordinator config, the real prompt of
the launcher, on the coordinator's own tick model. Nothing here stands in
for the agent.

One of the tick's GitHub calls is pointed at a blackhole of this machine's
own: a listening port that accepts the connection and never answers, so the
call waits with no client timeout of its own. The launcher's own log, lock
and skip log are moved to a scratch folder, so the proof does not touch the
live ones, and the repository's own `overnight` is put first on the tick's
PATH, so the tick runs the code of this branch.

    /opt/homebrew/bin/python3 evidence/MO-1057/proof.py
"""
import importlib.util
import os
import socket
import sys
import tempfile
import threading
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TICK = ROOT / "coordinator" / "pi" / "bin" / "coord-tick"
OVERNIGHT_DIR = ROOT / "coordinator" / "overnight"
SKIP_LOG = Path.home() / "Library/Logs/coordinator/skips.log"
# The one repository whose GitHub call hangs.
HUNG_REPO = "shyamsivakumar/mac-ops"

BLACKHOLE_GH = """#!/bin/sh
# One GitHub call pointed at a blackhole: the port accepts and never
# answers, so the call waits with no client timeout of its own. Every
# other call goes to the real GitHub.
for argument in "$@"; do
  if [ "$argument" = "{repo}" ]; then
    exec /usr/bin/curl -sS --connect-timeout 600 --max-time 600 \\
      http://127.0.0.1:{port}/github
  fi
done
exec /opt/homebrew/bin/gh "$@"
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
            # is named by OVERNIGHT_GH, so the ticket CLI still reaches
            # the real GitHub.
            blackhole_dir = home / "blackhole"
            blackhole_dir.mkdir()
            gh = blackhole_dir / "gh"
            gh.write_text(BLACKHOLE_GH.format(port=port, repo=HUNG_REPO))
            gh.chmod(0o755)
            log = home / "tick.log"
            os.environ["COORD_TICK_LOG"] = str(log)
            os.environ["COORD_TICK_LOCK"] = str(home / "coord-tick.lock")
            os.environ["OVERNIGHT_GH"] = str(gh)
            # The tick runs this branch's overnight, and the real agent
            # runs on the real pi with the launcher's own prompt.
            tick.CHILD_PATH = f"{OVERNIGHT_DIR}:{tick.CHILD_PATH}"
            tick.LOG_PATH = log
            before = skip_lines()
            started = time.monotonic()
            code = tick.main()
            elapsed = time.monotonic() - started
            after = skip_lines()
            print(f"tick exit={code} elapsed={elapsed:.0f}s")
            print("--- the tick log")
            print(log.read_text().rstrip() if log.exists() else "(no log)")
            print("--- the calls the tick skipped")
            new = after[len(before):]
            for line in new[:3]:
                print(line)
            print(f"--- skipped calls: {len(new)}")
            ok = elapsed < 600 and code == 0 and bool(new)
            print(f"--- the tick finished under 600 seconds: {ok}")
            return 0 if ok else 1
    finally:
        stop.set()
        server.close()


def skip_lines() -> list[str]:
    """The skip log's lines, if the log is there."""
    try:
        return [
            line
            for line in SKIP_LOG.read_text().splitlines()
            if "skipped" in line
        ]
    except OSError:
        return []


if __name__ == "__main__":
    sys.exit(main())
