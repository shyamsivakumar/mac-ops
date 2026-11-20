import json
import os
from pathlib import Path
import subprocess
import sys
import time

ALARM = "overnight-selftest"
EXECUTABLE = "overnight"
# The eval names the suite registers today. This set is what the hourly
# check compares against, and the suite's own registry is pinned to it in
# `hourly_selftest_fixture`, so the two cannot drift apart unnoticed.
EXPECTED = frozenset("send-integrity root-workspace worktree-base-ref consolidation-guard script-results start-routing "
                     "dead-run-recovery gate-pipeline merged-restart merge-pass gate-round-cap decisions-board-guard "
                     "no-parking turncap watchdog "
                     "zero-merge board-integrity api-budget ff-drift cycle-health "
                     "stall alarm-mute router-build router-blocked key-mint close-evidence".split())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=1) + "\n")
    os.replace(temporary, path)


def resolve_executable():
    """Return the overnight executable that belongs to this adapter.

    The installed adapter sits beside `~/.local/bin/overnight`; a run from
    the repository finds the checkout copy instead. When neither is there
    the reason says so, because a missing executable is a broken install
    and not a failing fixture suite."""
    script = Path(__file__).resolve()
    installed = script.with_name(EXECUTABLE)
    if installed.is_file():
        return installed, ""
    checkout = script.parent.parent / "overnight" / EXECUTABLE
    if checkout.is_file():
        return checkout, ""
    return None, (f"overnight executable not found: neither {installed} nor "
                  f"{checkout} exists")


def hourly(state_path, decisions_path, command, *, clock=time.time,
           runner=None, failure=""):
    # The runner is looked up when the check runs, not when this module is
    # imported, so a caller (the fixture) can stand a runner in its place.
    runner = runner or subprocess.run
    state_path, decisions_path = Path(state_path), Path(decisions_path)
    now = clock()
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if "last_run" in state and now - state["last_run"] < 3600:
        return "not-due"
    decisions = json.loads(decisions_path.read_text()) if decisions_path.exists() else {"items": []}
    if failure:
        passed, reason = False, failure
    else:
        try:
            result = runner(command, capture_output=True, text=True, timeout=120, check=False)
            lines = result.stdout.splitlines()
            names = [line[5:] for line in lines if line.startswith("PASS ")]
            passed = (result.returncode == 0 and len(names) == len(EXPECTED)
                      and set(names) == EXPECTED and len(lines) == len(EXPECTED))
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
    executable, reason = resolve_executable()
    state_path = home / ".local/state/mac-ops/overnight-selftest.json"
    decisions_path = home / "Code/coordinator/decisions.json"
    if executable is None:
        return hourly(state_path, decisions_path, [], failure=reason)
    command = [sys.executable, str(executable), "selftest"]
    return hourly(state_path, decisions_path, command)


if __name__ == "__main__":
    outcome = tick_selftest()
    print(outcome)
    raise SystemExit(1 if outcome == "FAIL" else 0)
