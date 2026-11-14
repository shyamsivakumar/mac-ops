import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, ".turn_cap.json")
TICKS = os.path.join(HERE, "ticks.log")
NOTES = os.path.join(HERE, "..", "notes.md")
CAP_SECONDS = 600
STOP_SECONDS = 1200
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
        state = {}
    state.setdefault("mis_sized", [])
    state.setdefault("stopped", [])
    state.setdefault("commented", [])
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


def log_hit(harness, thread, run_id, minutes, dry_run, kind="hit"):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    line = f"- cap {kind} {now} | {harness} | {thread['title']} | {run_id} | {minutes:.1f} min"
    if dry_run:
        print(f"DRY-RUN would log: {line}")
        return
    for path in (NOTES, TICKS):
        with open(path, "a") as f:
            f.write(line + "\n")


def ticket_url(data, run, thread):
    text = json.dumps({"run": run, "thread": data.get("thread", thread)})
    urls = set(re.findall(r"https://github.com/([\w.-]+/[\w.-]+)/issues/(\d+)", text))
    requests = set(re.findall(r"ticket:([\w.-]+/[\w.-]+)#(\d+):", text))
    tickets = urls | requests
    if len(tickets) != 1:
        raise ValueError("cannot identify exactly one ticket for stopped run")
    repo, number = tickets.pop()
    return f"https://github.com/{repo}/issues/{number}"


def handle_thread(harness, thread, state, dry_run):
    tid = thread["threadId"]
    data = call("t3mcp", "t3_thread_read", {"threadId": tid, "runLimit": 5, "limit": 1})
    runs = [r for r in data.get("recentRuns", []) if r.get("status") == "running"]
    if not runs:
        return
    run = max(runs, key=lambda r: r.get("ordinal", 0))
    run_id = run["runId"]
    elapsed = (datetime.now(timezone.utc) - parse_time(run["startedAt"])).total_seconds()
    if elapsed <= CAP_SECONDS:
        return
    if run_id not in state["mis_sized"]:
        log_hit(harness, thread, run_id, elapsed / 60, dry_run, kind="mis-sized")
        if not dry_run:
            state["mis_sized"].append(run_id)
            save_state(state)
    if elapsed <= STOP_SECONDS:
        return
    if run_id not in state["stopped"]:
        if dry_run:
            print(f"DRY-RUN would interrupt: {harness} {tid} {run_id}")
        else:
            call("t3mcp", "t3_thread_interrupt", {"threadId": tid, "runId": run_id})
            state["stopped"].append(run_id)
            save_state(state)
        log_hit(harness, thread, run_id, elapsed / 60, dry_run, kind="stopped")
    if run_id not in state["commented"]:
        url = ticket_url(data, run, thread)
        body = "Run passed 20 minutes; park for re-cut"
        if dry_run:
            print(f"DRY-RUN would gh issue comment {url} --body {body!r}")
        else:
            subprocess.run(
                ["gh", "issue", "comment", url, "--body", body],
                timeout=CALL_TIMEOUT, check=True, capture_output=True, text=True,
            )
            state["commented"].append(run_id)
            save_state(state)


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
                ValueError,
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
