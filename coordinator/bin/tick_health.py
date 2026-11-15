import os
from pathlib import Path
import re
import subprocess
import time


def tick_alarm():
    log = Path.home() / "Library/Logs/coordinator/tick.log"
    try:
        age = max(0, time.time() - log.stat().st_mtime)
    except OSError:
        age = None
    if age is not None and age <= 65 * 60:
        return ""
    loaded = "path = unavailable"
    try:
        result = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/dev.coordinator.tick"],
            capture_output=True, text=True, timeout=5,
        )
        match = re.search(r"^\s*(path = .+)$", result.stdout, re.MULTILINE)
        if result.returncode == 0 and match:
            loaded = match.group(1).strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    elapsed = "unavailable (missing or unreadable)" if age is None else f"{age / 60:.1f} minutes"
    return f"ALARM: tick.log age {elapsed}; {loaded}"
