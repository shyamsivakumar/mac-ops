import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def stale_log_alarm():
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


def job_exit_alarms(listing):
    alarms = []
    for line in listing.splitlines():
        fields = line.split("\t")
        if len(fields) != 3:
            continue
        _, status, label = fields
        if not label.startswith(("dev.coordinator.", "com.shyam.")):
            continue
        try:
            code = int(status)
        except ValueError:
            continue
        if code in (0, 78):
            continue
        alarms.append(f"ALARM: job {label} last exit {code}")
    return "\n".join(alarms)


def drift_alarm():
    receipt = Path.home() / ".local/state/mac-ops/coordinator-installation.json"
    marker = Path.home() / "Library/Logs/coordinator/install-drift.first-seen"
    try:
        checkout = Path(json.loads(receipt.read_text())["checkout"])
        result = subprocess.run(
            [sys.executable, str(checkout / "install_coordinator.py"), "status"],
            cwd=checkout, capture_output=True, text=True, timeout=30,
        )
        report = json.loads(result.stdout)
        if report["in_sync"]:
            marker.unlink(missing_ok=True)
            return ""
        now = time.time()
        if not marker.exists():
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(str(now))
        first_seen = float(marker.read_text())
        if now - first_seen < 1800:
            return ""
        names = ", ".join(Path(path).name for path in report["differs"][:5])
        minutes = int((now - first_seen) / 60)
        return (
            f"ALARM: installed coordinator differs from {checkout} "
            f"for {minutes} minutes: {names}"
        )
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError):
        return ""


def tick_alarm():
    listing = ""
    try:
        listing = subprocess.run(
            ["launchctl", "list"], capture_output=True, text=True, timeout=5,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "\n".join(
        part
        for part in (
            stale_log_alarm(),
            job_exit_alarms(listing),
            drift_alarm(),
        )
        if part
    )
