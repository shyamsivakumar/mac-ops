import json
import os
from pathlib import Path
import subprocess
import sys
import time

_OVERNIGHT_DIR = str(Path(__file__).resolve().parent.parent / "overnight")
if _OVERNIGHT_DIR not in sys.path:
    sys.path.append(_OVERNIGHT_DIR)
import alarms

ALARM = "overnight-selftest"
EXECUTABLE = "overnight"
# The eval names the suite registers today. This set is what the hourly
# check compares against, and the suite's own registry is pinned to it in
# `hourly_selftest_fixture`, so the two cannot drift apart unnoticed.
EXPECTED = frozenset("send-integrity root-workspace worktree-base-ref consolidation-guard script-results start-routing "
                     "dead-run-recovery gate-pipeline merged-restart merge-pass gate-round-cap decisions-board-guard "
                     "no-parking turncap watchdog "
                     "zero-merge board-integrity api-budget ff-drift cycle-health "
                     "stall alarm-mute router-build router-blocked key-mint credit-block close-evidence build-here "
                     "provider-until refill-busy journal-migration builder-receipt closed-ticket-merge inbox held-merge".split())


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
    card = {"id": ALARM, "group": "Coordinator", "kind": "action",
            "title": "Overnight fixture selftest failed", "why": reason}
    existing = alarms.read_board(decisions_path)[1]
    if passed and not (existing and any(isinstance(entry, dict) and entry.get("id") == ALARM
                                       for entry in existing["items"])):
        board = "wrote"
    else:
        board = alarms.board_update(decisions_path, ALARM, "raise" if not passed else "remove",
                                    card, create=True)
    state = {"last_run": now, "passed": passed}
    if board != "wrote":
        state["board"] = board
        print(f"decisions board not updated: {board}", file=sys.stderr)
    save(state_path, state)
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
