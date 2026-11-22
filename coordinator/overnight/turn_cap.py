import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

COORDINATOR_DIR = os.path.expanduser(
    os.environ.get("MAC_OPS_COORDINATOR_DIR") or "~/Code/coordinator"
)
LOOP_DIR = os.path.join(COORDINATOR_DIR, "loop")
STATE = os.path.join(LOOP_DIR, ".turn_cap.json")
TICKS = os.path.join(LOOP_DIR, "ticks.log")
NOTES = os.path.join(LOOP_DIR, "caps.log")
CAP_SECONDS = 1200
WARN_SECONDS = 600
RESUME_GAP_SECONDS = 60
POLL_SECONDS = 60
CALL_TIMEOUT = 30
T3_FALLBACK_PROJECTS = [
    "mcp:a187512a-ba4d-430a-826c-e305adc8f72e",
    "mcp:a55b7217-1c6b-462c-806f-81c1b9604f33",
]


def call(cli, tool, args):
    proc = subprocess.run(
        [cli, "call", tool, json.dumps(args)],
        capture_output=True,
        text=True,
        timeout=CALL_TIMEOUT,
        check=True,
    )
    return json.loads(proc.stdout, strict=False)


def parse_time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def load_state():
    if os.path.exists(STATE):
        with open(STATE) as f:
            state = json.load(f)
    else:
        state = {"handled": [], "wrapped": {}}
    state.setdefault("wrapped_at", {})
    state.setdefault("finalized", [])
    return state


def save_state(state):
    with open(STATE, "w") as f:
        json.dump(state, f)


def t3_project_ids():
    result = subprocess.run(
        ["t3mcp", "tools"],
        capture_output=True,
        text=True,
        timeout=CALL_TIMEOUT,
        check=False,
    )
    names = result.stdout.split()
    if "t3_project_list" in names:
        projects = call("t3mcp", "t3_project_list", {})
        return [p["id"] for p in projects.get("projects", [])]
    return T3_FALLBACK_PROJECTS


def running_threads(harness):
    for project_id in t3_project_ids():
        listing = call("t3mcp", "t3_thread_list", {"projectId": project_id})
        for thread in listing.get("threads", []):
            if thread.get("status") == "running":
                yield thread


def ticket_start(runs):
    timed = sorted(
        (r for r in runs if r.get("startedAt")), key=lambda r: r.get("ordinal", 0)
    )
    if not timed:
        return None
    start = parse_time(timed[-1]["startedAt"])
    for prev in reversed(timed[:-1]):
        ended = prev.get("completedAt")
        if (
            not ended
            or (start - parse_time(ended)).total_seconds() > RESUME_GAP_SECONDS
        ):
            break
        start = parse_time(prev["startedAt"])
    return start


def current_run(cli, read_tool, thread):
    data = call(
        cli, read_tool, {"threadId": thread["threadId"], "runLimit": 5, "limit": 1}
    )
    runs = data.get("recentRuns", [])
    running = [r for r in runs if r.get("status") == "running"]
    run = max(running, key=lambda r: r.get("ordinal", 0), default=None)
    if run and run.get("startedAt"):
        return (
            run["runId"],
            run.get("ordinal", 0),
            parse_time(run["startedAt"]),
            parse_time(run["startedAt"]),
            False,
        )
    return None


def log_hit(harness, thread, run_id, minutes, dry_run, kind="hit"):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    line = f"- cap {kind} {now} | {harness} | {thread['title']} | {run_id} | {minutes:.1f} min"
    if dry_run:
        print(f"DRY-RUN would log: {line}")
        return
    for path in (NOTES, TICKS):
        with open(path, "a") as f:
            f.write(line + "\n")
    print(line)


def handle_thread(harness, thread, state, dry_run):
    active = current_run("t3mcp", "t3_thread_read", thread)
    if active is None:
        return
    run_id, _, started, _, _ = active
    now = datetime.now(timezone.utc)
    tid = thread["threadId"]
    if "staging test and promote" in thread["title"].lower():
        return
    clock = state.setdefault("clocks", {}).setdefault(
        f"{tid}:{run_id}", {"paused": 0, "waiting_since": None}
    )
    if "WAITING: heavy busy" in thread.get("message", ""):
        if clock["waiting_since"] is None:
            clock["waiting_since"] = now.timestamp()
        if not dry_run:
            save_state(state)
        return
    if clock["waiting_since"] is not None:
        clock["paused"] += max(0, now.timestamp() - clock["waiting_since"])
        clock["waiting_since"] = None
    age = (now - started).total_seconds() - clock["paused"]
    if run_id in state["handled"]:
        return
    warning_key = f"{tid}:{run_id}"
    if age > WARN_SECONDS and warning_key not in state.setdefault("warned", []):
        log_hit(harness, thread, run_id, age / 60, dry_run, kind="mis-sized")
        if not dry_run:
            state["warned"].append(warning_key)
    if age > CAP_SECONDS:
        if dry_run:
            print(f"DRY-RUN would interrupt and park: {harness} {tid} {run_id}")
            return
        call("t3mcp", "t3_thread_interrupt", {"threadId": tid, "runId": run_id})
        log_hit(harness, thread, run_id, age / 60, dry_run)
        state["handled"].append(run_id)
        if tid not in state.setdefault("parked", []):
            state["parked"].append(tid)
    if not dry_run:
        save_state(state)


def load_handler():
    return sys.modules[__name__]


def one_pass(dry_run):
    state = load_state()
    for harness in ["t3"]:
        try:
            threads = list(running_threads(harness))
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as e:
            print(f"{harness} thread list failed: {e}", file=sys.stderr)
            continue
        print(f"{harness}: {len(threads)} running thread(s)")
        for thread in threads:
            try:
                handle_thread(harness, thread, state, dry_run)
            except (
                subprocess.SubprocessError,
                json.JSONDecodeError,
                OSError,
                KeyError,
            ) as e:
                print(
                    f"{harness} {thread.get('threadId')} failed: {e}", file=sys.stderr
                )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    while True:
        one_pass(args.dry_run)
        if args.once:
            return
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
