import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import journal

HOLD_REASONS = ("loop code hold", "prompt hold")
MERGED = ("merged", "merged_outside_lane")
STOP_DAYS = 7 * 86400
TICK_RUN_S = 600
TICK_LINE = re.compile(
    r"^(\d{4}-\d\d-\d\d \d\d:\d\d) ([A-Z]{2,5}) \| tick \| exit=0\b", re.MULTILINE
)


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
    cache = marker.with_name("install-drift.status.json")
    try:
        checkout = Path(json.loads(receipt.read_text())["checkout"])
        now = time.time()
        try:
            report = json.loads(cache.read_text())
        except (OSError, ValueError):
            report = {"checked": 0}
        if now - report["checked"] >= 600:
            result = subprocess.run(
                [sys.executable, str(checkout / "install_coordinator.py"), "status", "--no-smoke"],
                cwd=checkout, capture_output=True, text=True, timeout=30,
            )
            status = json.loads(result.stdout)
            report = {
                "checked": now,
                "in_sync": status["in_sync"],
                "differs": status["differs"],
                "config_key_drift": status["config_key_drift"],
            }
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(report))
        key_drift = report.get("config_key_drift", [])
        if report["in_sync"] and not key_drift:
            marker.unlink(missing_ok=True)
            return ""
        if not marker.exists():
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(str(now))
        first_seen = float(marker.read_text())
        if now - first_seen < 1800:
            return ""
        names = ", ".join(
            [Path(path).name for path in report["differs"][:5]] + key_drift[:5]
        )
        minutes = int((now - first_seen) / 60)
        return (
            f"ALARM: installed coordinator differs from {checkout} "
            f"for {minutes} minutes: {names}"
        )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return ""


def limit(value, default, whole=False):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number) or number <= 0 or (whole and number != int(number)):
        return default
    return int(number) if whole else number


def rows_by_pr(rows):
    grouped = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ts, repo, pr = row.get("ts"), row.get("repo"), row.get("pr")
        if (
            isinstance(ts, bool)
            or not isinstance(ts, (int, float))
            or not math.isfinite(ts)
        ):
            continue
        if not isinstance(repo, str) or isinstance(pr, bool) or not isinstance(pr, int):
            continue
        grouped.setdefault((repo, pr), []).append((ts, row))
    for seq in grouped.values():
        seq.sort(key=lambda pair: pair[0])
    return grouped


def held_alarm(rows, *, now, hours):
    hours = limit(hours, 6)
    alarms = []
    for (repo, pr), seq in rows_by_pr(rows).items():
        head = next(
            (
                r["head"]
                for _, r in reversed(seq)
                if isinstance(r.get("head"), str) and r["head"]
            ),
            None,
        )
        holds = [
            (ts, r["data"]["reason"])
            for ts, r in seq
            if r.get("event") == "merge_held"
            and r.get("head") == head
            and isinstance(r.get("data"), dict)
            and r["data"].get("reason") in HOLD_REASONS
        ]
        if not holds:
            continue
        held, reason = holds[-1]
        age = now - held
        if age <= hours * 3600 or age > STOP_DAYS:
            continue
        if any(r.get("event") in MERGED and ts >= held for ts, r in seq):
            continue
        alarms.append(
            f"ALARM: {repo}#{pr} held {age / 3600:.1f} h ({reason}), no merge since"
        )
    return "\n".join(sorted(alarms))


def idle_alarm(rows, ticks, *, now, count):
    count = limit(count, 8, whole=True)
    rows = list(rows)
    if len(ticks) < count:
        return ""
    start = sorted(ticks)[-count] - TICK_RUN_S
    for row in rows:
        data = row.get("data") if isinstance(row, dict) else None
        ts = row.get("ts") if isinstance(data, dict) and data.get("via_tick") else None
        if isinstance(ts, (int, float)) and not isinstance(ts, bool) and ts >= start:
            return ""
    waiting = []
    for (repo, pr), seq in rows_by_pr(rows).items():
        ts, last = seq[-1]
        data = last.get("data")
        if (
            last.get("event") == "gate_verdict"
            and isinstance(data, dict)
            and data.get("verdict") == "FAIL"
            and ts < start
            and now - ts <= STOP_DAYS
        ):
            waiting.append(f"{repo}#{pr}")
    if not waiting:
        return ""
    return f"ALARM: {count} finished ticks did nothing; gate FAIL waiting on {', '.join(sorted(waiting))}"


def finished_ticks(text):
    ticks = []
    for stamp, zone in TICK_LINE.findall(text):
        parsed = time.strptime(stamp, "%Y-%m-%d %H:%M")
        dst = (
            1
            if time.daylight and zone == time.tzname[1]
            else 0
            if zone == time.tzname[0]
            else -1
        )
        ticks.append(time.mktime(tuple(parsed)[:8] + (dst,)))
    return ticks


def journal_rows(now):
    paths = {journal.journal_path(moment) for moment in (now, now - STOP_DAYS - 86400)}
    for path in sorted(paths):
        try:
            with open(path) as handle:
                for line in handle:
                    if '"pr":null' in line and '"via_tick"' not in line:
                        continue
                    try:
                        yield json.loads(line)
                    except ValueError:
                        continue
        except OSError:
            continue


def stop_rules_alarm():
    if os.environ.get("COORD_STOP_RULES") != "on":
        return ""
    now = time.time()
    log = Path.home() / "Library/Logs/coordinator/tick.log"
    try:
        with open(log, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - 262144))
            ticks = finished_ticks(handle.read().decode("utf-8", "replace"))
    except OSError:
        ticks = []
    rows = list(journal_rows(now))
    return "\n".join(
        part
        for part in (
            held_alarm(rows, now=now, hours=os.environ.get("COORD_HELD_HOURS")),
            idle_alarm(rows, ticks, now=now, count=os.environ.get("COORD_IDLE_TICKS")),
        )
        if part
    )


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
            stop_rules_alarm(),
        )
        if part
    )
