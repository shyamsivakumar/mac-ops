#!/usr/bin/env python3
"""Drive board_restart.tick with a fixture. No live board, no new test file."""

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "board_restart.py"
BASE = 1_700_000_000.0
GONE = int((BASE - 200) * 1000)
CYCLE = ("claude", "gpt")


def load(path):
    spec = importlib.util.spec_from_file_location("restart_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row(gone=GONE):
    return {
        "id": "mac-ops/1",
        "state": "error",
        "stage": "working",
        "msg": "The agent has exited",
    }, {
        "exitedAt": gone,
        "agent": "claude",
        "link": {"pane": "p1"},
    }


def panes(session):
    return {"p1": {"session": session, "agent": "claude", "status": "working"}}


def tick(module, now, state, gone=GONE, session="s1", tasks=None):
    body, meta = row(gone)
    if tasks is None:
        tasks = {"mac-ops/1": meta}
    return module.tick(
        now=now,
        dry_run=True,
        rows=[body],
        panes=panes(session),
        tasks=tasks,
        state_path=state,
        cycle=CYCLE,
    )


def restarts(result):
    return [item for item in result["actions"] if item.get("action") == "restart"]


def tells(result):
    return [item for item in result["actions"] if item.get("action") == "tell"]


def scenario_same_exit(module, state):
    first = tick(module, BASE, state)
    second = tick(module, BASE + 61, state)
    third = tick(module, BASE + 122, state, session="s2")
    return first, second, third


def scenario_newer(module, state):
    scenario_same_exit(module, state)
    newer = int((BASE + 31) * 1000)
    return tick(module, BASE + 183, state, gone=newer)


def scenario_retry(module, state):
    calls = {"n": 0}
    real = module.run_command

    def flaky(command, _dry_run):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "command": [str(part) for part in command],
                "ok": False,
                "error": "stub",
            }
        return real(command, True)

    module.run_command = flaky
    try:
        tick(module, BASE, state)
        failed = tick(module, BASE + 61, state)
        retried = tick(module, BASE + 62, state)
    finally:
        module.run_command = real
    return failed, retried


def scenario_crash(module, state):
    calls = {"n": 0}
    real_restart = module.restart
    real_write = module.write_state

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real_restart(*args, **kwargs)

    def boom(_state_body, path=module.STATE):
        raise OSError("replace failed")

    tick(module, BASE, state)
    module.restart = counting
    module.write_state = boom
    raised = False
    try:
        tick(module, BASE + 61, state)
    except OSError:
        raised = True
    module.write_state = real_write
    tick(module, BASE + 62, state)
    module.restart = real_restart
    return raised, calls["n"]


def check(module):
    with tempfile.TemporaryDirectory(prefix="restart-latch-") as directory:
        root = Path(directory)
        first, second, third = scenario_same_exit(module, root / "same.json")
        if (
            restarts(first)
            or len(restarts(second)) != 1
            or restarts(third)
            or len(tells(third)) != 1
        ):
            raise SystemExit(
                f"same exit: first {len(restarts(first))} second {len(restarts(second))} "
                f"third {len(restarts(third))} tells {len(tells(third))}"
            )
        newer = scenario_newer(module, root / "newer.json")
        if len(restarts(newer)) != 1:
            raise SystemExit(f"newer exit restarted {len(restarts(newer))} times")
        failed, retried = scenario_retry(module, root / "retry.json")
        if (
            failed["actions"][0]["result"]["ok"]
            or len(restarts(retried)) != 1
            or not retried["actions"][0]["result"]["ok"]
        ):
            raise SystemExit("failed command did not retry on the next tick")
        raised, count = scenario_crash(module, root / "crash.json")
        if not raised or count != 2:
            raise SystemExit(
                f"crash gap changed: raised {raised} restart calls {count}"
            )
    print(
        "replay: one restart per exit, retry after failure, tell without a second restart"
    )
    print(
        "KNOWN GAP crash: write_state raised after restart(); the next tick restarted again"
    )
    return 0


def mutant(module):
    with tempfile.TemporaryDirectory(prefix="restart-latch-mut-") as directory:
        _, second, _third = scenario_same_exit(module, Path(directory) / "state.json")
        # Third tick is +122s. Without the latch the 60s clock reset on success,
        # so a fourth tick is required. Run one more.
        fourth = tick(module, BASE + 183, Path(directory) / "state.json")
    repeat = len(restarts(second)) + len(restarts(fourth))
    if len(restarts(second)) != 1 or len(restarts(fourth)) < 1:
        raise SystemExit(
            f"mutant did not double-restart (second {len(restarts(second))} later {len(restarts(fourth))})"
        )
    print(f"mutant: same exit restarted {repeat} times")
    return 0


def write_mutant(dest):
    text = SOURCE.read_text(encoding="utf-8")
    guard = '            if record.get("restarted_exit") == gone_at:\n                continue\n'
    setter = '            if signature == "agent_exited":\n                record["restarted_exit"] = meta.get("exitedAt")\n'
    if guard not in text or setter not in text:
        raise SystemExit("latch lines not found in board_restart.py")
    dest.write_text(text.replace(guard, "", 1).replace(setter, "", 1), encoding="utf-8")
    print(f"mutant written {dest}")


def main(argv):
    command = argv[1] if len(argv) > 1 else "check"
    if command == "mutate":
        write_mutant(Path(argv[2]))
        return 0
    path = SOURCE
    if command == "module":
        path = Path(argv[2])
        command = argv[3]
    module = load(path)
    if command == "check":
        return check(module)
    if command == "mutant":
        return mutant(module)
    raise SystemExit(f"unknown command {command}")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
