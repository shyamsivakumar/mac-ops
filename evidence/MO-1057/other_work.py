#!/usr/bin/env python3
"""The tick's other work, read for real.

The checks are the ones of `loop/tick.md` section 2 that need no GitHub:
the lane driver's log, the dispatcher's last write, the shift's log, the
tracebacks in the last lines of the queue logs, the launchd job and the
decisions log. Every line holds a measured value, so a reader can see the
checks ran and what they read.

    /opt/homebrew/bin/python3 evidence/MO-1057/other_work.py
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HOME = Path.home()
LOGS = HOME / "Library/Logs/coordinator"
COORD = HOME / "Code/coordinator"
QUEUE = COORD / "queue"


def age(path: Path) -> str:
    """The age of a file in seconds, or the reason it is not known."""
    try:
        return f"{int(time.time() - path.stat().st_mtime)}s"
    except OSError as exc:
        return f"unknown ({exc.strerror})"


def tracebacks(path: Path, lines: int = 40) -> str:
    """The tracebacks in the last lines of a log."""
    try:
        with open(path, "rb") as stream:
            size = stream.seek(0, os.SEEK_END)
            start = max(0, size - 512 * 1024)
            stream.seek(start)
            text = stream.read().decode("utf-8", errors="replace")
    except OSError as exc:
        return f"unknown ({exc.strerror})"
    return str(len([l for l in text.splitlines()[-lines:] if "Traceback" in l]))


def launchd(label: str) -> str:
    """Whether the launchd job resolves, and its state."""
    try:
        result = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{label}"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"unknown ({exc})"
    if result.returncode != 0:
        return "does not resolve"
    for line in result.stdout.splitlines():
        if line.strip().startswith("state ="):
            return line.strip()
    return "resolves"


def main() -> int:
    checks = [
        # The lane driver's log is the one loop/tick.md names:
        # `loop/lanes.log`, in the coordinator's own folder.
        ("lanes", f"loop/lanes.log age {age(COORD / 'loop' / 'lanes.log')}"),
        ("dispatch", f"last write age {age(QUEUE / 'dispatch.last')}"),
        ("overnight", f"log age {age(LOGS / 'overnight.log')}"),
        ("traceback", f"dispatch {tracebacks(QUEUE / 'dispatch.log')}"),
        ("gatekeep", f"traceback {tracebacks(QUEUE / 'gatekeep.log')}"),
        ("launchd", f"dev.coordinator.lanes {launchd('dev.coordinator.lanes')}"),
    ]
    decisions = COORD / "decisions.json"
    try:
        items = len(json.loads(decisions.read_text()).get("items") or [])
        checks.append(("decisions", f"{items} item(s)"))
    except (OSError, ValueError) as exc:
        checks.append(("decisions", f"unknown ({exc})"))
    for name, value in checks:
        print(f"{name}: {value}")
    print(f"read at {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
