import json
import os
from pathlib import Path
import subprocess
import sys
import time

ALARM = "overnight-selftest"
EXPECTED = set("start-routing gate-pipeline no-parking turncap watchdog zero-merge board-integrity api-budget ff-drift script-results consolidation-guard send-integrity".split())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=1) + "\n")
    os.replace(temporary, path)


def hourly(state_path, decisions_path, command, *, clock=time.time, runner=subprocess.run):
    state_path, decisions_path = Path(state_path), Path(decisions_path)
    now = clock()
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if "last_run" in state and now - state["last_run"] < 3600:
        return "not-due"
    decisions = json.loads(decisions_path.read_text()) if decisions_path.exists() else {"items": []}
    try:
        result = runner(command, capture_output=True, text=True, timeout=120, check=False)
        lines = result.stdout.splitlines()
        names = [line[5:] for line in lines if line.startswith("PASS ")]
        passed = result.returncode == 0 and len(names) == 12 and set(names) == EXPECTED and len(lines) == 12
        reason = "fixture suite failed" if not passed else ""
    except (OSError, subprocess.SubprocessError) as exc:
        passed, reason = False, type(exc).__name__
    decisions["items"] = [item for item in decisions.get("items", []) if item.get("id") != ALARM]
    if not passed:
        decisions["items"].append({"id": ALARM, "group": "Coordinator", "kind": "action",
                                   "title": "Overnight fixture selftest failed", "why": reason})
    save(decisions_path, decisions)
    save(state_path, {"last_run": now, "passed": passed})
    return "PASS" if passed else "FAIL"


def tick_selftest():
    home = Path.home()
    command = [sys.executable, str(Path(__file__).resolve().parents[1] / "overnight" / "overnight"), "selftest"]
    return hourly(home / ".local/state/mac-ops/overnight-selftest.json",
                  home / "Code/coordinator/decisions.json", command)
