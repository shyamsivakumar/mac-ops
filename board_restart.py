#!/usr/bin/env python3
"""Restart board tasks whose agent died, with the board's own commands.

The controller calls this once a minute. A row whose agent is gone is
remembered; the same row seen again a minute later is handed to the next agent
of the cycle, and told what happened. The board keeps the branch, the worktree
and the wait the task had.
"""
import argparse
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

CYCLE = ("omp/openai-codex/gpt-6.1-terra", "codex/gpt-6.1-terra", "claude")
STATE = Path.home() / ".local" / "state" / "mac-ops" / "board-restart.state.json"
BOARD_HOME = Path(os.environ.get("HERDR_PROJECTS_HOME") or (Path.home() / ".herdr-projects"))
BOARD_CMD = BOARD_HOME / "data" / "bin" / "herdr-projects"
TASKS = BOARD_HOME / "data" / "tasks"
HERDR_CMD = "herdr"
MIN_INTERVAL_SECONDS = 60.0
MAX_RESTARTS_PER_HOUR = 3
MAX_RESTARTS_PER_HOUR_BOARD = 6
RESTART_WINDOW_SECONDS = 3600.0
TELL_AFTER_SECONDS = 20.0
PENDING_TELL_SECONDS = 900.0
COMMAND_TIMEOUT = 60
MACHINE_WIDE_CAUSES = (
    "herdr did not answer",
    "shell was not ready",
    "start was cut off",
    "terminal was not at its shell prompt",
    "did not come up within a minute",
    "not a git repository",
)
DEAD_AGENT_SECONDS = 90.0
TELL_TEXT = ("Restarted on {agent} after {reason}; your branch and work are kept; "
             "continue from your last step.")


def board_rows():
    output = subprocess.run([str(BOARD_CMD), "list", "--json"], check=True, capture_output=True,
                            text=True, timeout=COMMAND_TIMEOUT).stdout
    rows = json.loads(output)
    if not isinstance(rows, list):
        raise ValueError("the board's rows are not a list")
    return [row for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str)]


def task_file(task_id):
    parts = task_id.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1].isdigit():
        raise ValueError("the task's identity is not repo/number")
    return TASKS / parts[0] / parts[1] / "task.json"


def task_meta(task_id):
    try:
        path = task_file(task_id)
        if path.stat().st_size > 1_000_000:
            return {}
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return {}
    return meta if isinstance(meta, dict) else {}


def pane_agents():
    """What each pane of the session runs, by pane id."""
    try:
        output = subprocess.run([HERDR_CMD, "pane", "list"], check=True, capture_output=True,
                                text=True, timeout=COMMAND_TIMEOUT).stdout
        data = json.loads(output)
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        return {}
    panes = data.get("result", {}).get("panes") if isinstance(data, dict) else None
    if not isinstance(panes, list):
        return {}
    found = {}
    for pane in panes:
        if not isinstance(pane, dict):
            continue
        pane_id = pane.get("pane_id")
        if not isinstance(pane_id, str):
            continue
        session = pane.get("agent_session")
        session_id = session.get("value") if isinstance(session, dict) else None
        found[pane_id] = {"agent": pane.get("agent"), "status": pane.get("agent_status"),
                          "session": session_id if isinstance(session_id, str) else None}
    return found


def classify(row, meta):
    """The dead-agent signature of a row, or None when the row is not dead."""
    stage = row.get("stage")
    state = row.get("state")
    message = (row.get("msg") or "").strip()
    failure = meta.get("failure")
    failure_stage = failure.get("stage") if isinstance(failure, dict) else None
    if state == "error" and stage == "working" and message in ("The agent has exited",
                                                                "The agent's terminal is gone"):
        return "agent_exited"
    if stage == "failed":
        if failure_stage in ("start", "setup") or message.startswith("Could not start:"):
            return "could_not_start"
        if failure_stage == "send" or message.startswith("Not started:"):
            return "not_started"
    if stage == "working" and message.startswith("Has not started yet"):
        return "has_not_started_yet"
    return None


def exclusion(row, meta):
    """Why a row is never touched, or None when it may be restarted."""
    if row.get("archivedAt") or meta.get("archivedAt"):
        return "archived"
    if row.get("research") or meta.get("researchRun"):
        return "research"
    if row.get("state") == "blocked":
        return "blocked"
    if row.get("kind") in ("question", "permission", "auth") or meta.get("kind"):
        return "blocked_on_question"
    if meta.get("blocked") or meta.get("selfBlocked"):
        return "blocked"
    stage = row.get("stage")
    if stage in ("reviewing", "reviewneeds"):
        return "in_review"
    if stage in ("approval", "asks", "plan"):
        return "waiting_on_you"
    if stage in ("done", "stopped", "nosummary", "after", "todo", "queued", "starting", "setup",
                 "checking", "pushing", "merging", "progress", "attempts", "pick", "tried"):
        return "stage_" + stage
    if (meta.get("expectedWake") or {}).get("reason") == "review" or meta.get("turnBy") == "reviewer":
        return "in_review"
    if (row.get("msg") or "").strip() == "Finishing":
        return "finishing"
    return None


def next_agent(failed, cursor, cycle=CYCLE):
    """The next agent of the cycle, skipping the one that failed."""
    if not cycle:
        raise ValueError("the cycle is empty")
    if not 0 <= cursor < len(cycle):
        cursor = 0
    start = cycle.index(failed) + 1 if failed in cycle else cursor
    for step in range(len(cycle)):
        index = (start + step) % len(cycle)
        if cycle[index] != failed:
            return cycle[index], (index + 1) % len(cycle)
    raise ValueError("the cycle has no other agent")


def failed_agent(meta, row, cycle=CYCLE):
    """The agent that ran and failed, as the cycle names it."""
    settings = meta.get("settings")
    if isinstance(settings, dict):
        agent = settings.get("worker.agent")
        if isinstance(agent, str) and agent:
            return agent if agent in cycle else None
    agent = meta.get("agent")
    return agent if isinstance(agent, str) and agent in cycle else None


def after_ids(meta):
    waits = meta.get("after")
    if not isinstance(waits, list):
        return []
    return [wait for wait in waits if isinstance(wait, str) and wait]


def read_state(path=STATE):
    try:
        info = os.lstat(str(path))
    except FileNotFoundError:
        return {"schema": 1, "cursor": 0, "tasks": {}}
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("the restart state file is unsafe")
    if info.st_size > 1_000_000:
        raise ValueError("the restart state file is too large")
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or state.get("schema") != 1 or not isinstance(state.get("tasks"), dict):
        raise ValueError("the restart state file has an unknown shape")
    cursor = state.get("cursor")
    if not isinstance(cursor, int) or isinstance(cursor, bool) or cursor < 0:
        state["cursor"] = 0
    return state


def write_state(state, path=STATE):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    payload = json.dumps(state, allow_nan=False, separators=(",", ":")).encode("utf-8")
    handle = os.open(str(temporary), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        os.write(handle, payload)
    finally:
        os.close(handle)
    os.replace(str(temporary), str(path))


def restarts_in_window(record, now):
    stamps = record.get("restarts")
    if not isinstance(stamps, list):
        return 0
    return sum(1 for stamp in stamps
               if isinstance(stamp, (int, float)) and not isinstance(stamp, bool)
               and now - stamp < RESTART_WINDOW_SECONDS)


def board_restarts_in_window(records, now):
    total = 0
    for record in records.values():
        if isinstance(record, dict):
            total += restarts_in_window(record, now)
    return total


def agent_is_up(meta, panes, pending):
    """Whether the agent that was started after the restart is running now."""
    since = pending.get("at", 0)
    started = meta.get("startedAgentAt")
    if isinstance(started, (int, float)) and not isinstance(started, bool) and started / 1000 > since:
        return True
    last = meta.get("last")
    if isinstance(last, dict):
        at = last.get("at")
        if isinstance(at, (int, float)) and not isinstance(at, bool) and at / 1000 > since:
            return True
    pane = pending.get("pane")
    session = pending.get("session")
    if pane and session:
        current = (panes.get(pane) or {}).get("session")
        if current and current != session:
            return True
    return False


def run_command(command, dry_run):
    shown = [str(part) for part in command]
    if dry_run:
        return {"command": shown, "ok": True, "dry_run": True}
    try:
        done = subprocess.run(shown, capture_output=True, text=True, timeout=COMMAND_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"command": shown, "ok": False,
                "error": type(exc).__name__ + ": " + str(exc).splitlines()[0][:160]}
    said = (done.stdout or "").strip().splitlines()
    return {"command": shown, "ok": done.returncode == 0, "returncode": done.returncode,
            "output": (said[-1][:200] if said else ""),
            "error": (done.stderr or "").strip().splitlines()[:1][0][:200] if done.returncode else ""}


def restart(task_id, agent, reason, signature, dry_run, waits_before):
    """The board's own commands: the agent is stopped, the next one starts."""
    steps = []
    if signature == "not_started":
        # The board's own restart: the program that never took the text is ended and
        # started again with the same text, on the agent the cycle names.
        set_agent = run_command([BOARD_CMD, "set", "worker.agent", agent, "--task", task_id], dry_run)
        steps.append(set_agent)
        if not set_agent["ok"]:
            return {"task": task_id, "agent": agent, "steps": steps, "ok": False}
        steps.append(run_command([BOARD_CMD, "retry", task_id], dry_run))
    else:
        steps.append(run_command([BOARD_CMD, "stop", task_id], dry_run))
        if not steps[-1]["ok"]:
            return {"task": task_id, "agent": agent, "steps": steps, "ok": False}
        steps.append(run_command([BOARD_CMD, "delegate", task_id, "--worker.agent", agent], dry_run))
    ok = all(step["ok"] for step in steps)
    return {"task": task_id, "agent": agent, "steps": steps, "ok": ok,
            "tell": TELL_TEXT.format(agent=agent, reason=reason),
            "wait_before": waits_before}


def tick(*, now=None, dry_run=False, rows=None, panes=None, tasks=None, state_path=STATE, cycle=CYCLE):
    now = time.time() if now is None else now
    state = read_state(state_path)
    records = state["tasks"]
    rows = board_rows() if rows is None else rows
    panes = pane_agents() if panes is None else panes
    tasks = tasks if isinstance(tasks, dict) else None
    actions = []
    seen = set()
    for row in rows:
        task_id = row["id"]
        if tasks is not None:
            meta = tasks.get(task_id)
            meta = meta if isinstance(meta, dict) else {}
        else:
            meta = task_meta(task_id)
        signature = classify(row, meta)
        record = records.get(task_id)
        if not isinstance(record, dict):
            record = {}
            records[task_id] = record
        pending = record.get("pending_tell")
        if isinstance(pending, dict):
            finished = ((row.get("msg") or "").strip() == "Finishing"
                        or row.get("stage") in ("done", "nosummary"))
            if finished:
                record.pop("pending_tell", None)
            elif now - pending.get("at", 0) > PENDING_TELL_SECONDS:
                record.pop("pending_tell", None)
            elif now - pending.get("at", 0) >= TELL_AFTER_SECONDS and agent_is_up(meta, panes, pending):
                told = run_command([BOARD_CMD, "tell", task_id, pending["text"]], dry_run)
                actions.append({"task": task_id, "action": "tell", "steps": [told]})
                record.pop("pending_tell", None)
        if signature is None:
            continue
        seen.add(task_id)
        if record.get("signature") != signature:
            record["signature"] = signature
            record["first_seen"] = now
            record.pop("skip", None)
        reason = (row.get("msg") or "").strip()
        if reason != record.get("reason"):
            record["reason"] = reason
            record.pop("skip", None)
        skip = exclusion(row, meta)
        if skip:
            record["skip"] = skip
            continue
        # A cap is a count of the last hour, so it is decided again each pass.
        if record.get("skip") in ("restart_cap", "board_restart_cap"):
            record.pop("skip", None)
        if record.get("skip"):
            continue
        if not reason:
            record["skip"] = "no_reason"
            continue
        cause = reason.lower()
        if signature == "could_not_start" and any(word in cause for word in MACHINE_WIDE_CAUSES):
            record["skip"] = "machine_wide_failure"
            continue
        if signature == "agent_exited":
            # The board writes the time it saw the agent go; an agent that ended its turn
            # normally leaves that time fresh, and its work is done.
            gone_at = meta.get("exitedAt")
            if not isinstance(gone_at, (int, float)) or isinstance(gone_at, bool):
                record["skip"] = "no_exit_time"
                continue
            if now - gone_at / 1000 < DEAD_AGENT_SECONDS:
                continue
        if now - record.get("first_seen", now) < MIN_INTERVAL_SECONDS:
            continue
        if restarts_in_window(record, now) >= MAX_RESTARTS_PER_HOUR:
            record["skip"] = "restart_cap"
            continue
        if board_restarts_in_window(records, now) >= MAX_RESTARTS_PER_HOUR_BOARD:
            record["skip"] = "board_restart_cap"
            continue
        agent, cursor = next_agent(failed_agent(meta, row, cycle), state["cursor"], cycle)
        state["cursor"] = cursor
        waits_before = after_ids(meta)
        pane = (meta.get("link") or {}).get("pane")
        session = (panes.get(pane) or {}).get("session") if isinstance(pane, str) else None
        result = restart(task_id, agent, reason, signature, dry_run, waits_before)
        stamps = record.get("restarts")
        stamps = stamps if isinstance(stamps, list) else []
        record["restarts"] = stamps
        if result["ok"]:
            stamps.append(now)
            record["first_seen"] = now
            record.pop("skip", None)
            record["pending_tell"] = {"at": now, "text": result["tell"], "agent": agent,
                                      "pane": pane if isinstance(pane, str) else None,
                                      "session": session}
            waits_after = after_ids(meta if tasks is not None else task_meta(task_id))
            result["wait_after"] = waits_after
            result["wait_kept"] = waits_after == waits_before
        actions.append({"task": task_id, "action": "restart", "signature": signature,
                        "reason": reason, "result": result})
    for task_id in list(records):
        record = records[task_id]
        if not isinstance(record, dict):
            records.pop(task_id)
            continue
        if task_id not in seen:
            record.pop("first_seen", None)
            record.pop("signature", None)
            record.pop("reason", None)
            record.pop("skip", None)
        stamps = record.get("restarts")
        if isinstance(stamps, list):
            record["restarts"] = [stamp for stamp in stamps
                                  if isinstance(stamp, (int, float)) and not isinstance(stamp, bool)
                                  and now - stamp < RESTART_WINDOW_SECONDS]
        if not record:
            records.pop(task_id)
    write_state(state, state_path)
    return {"schema": 1, "at": now, "dry_run": bool(dry_run), "actions": actions,
            "cursor": state["cursor"], "cycle": list(cycle)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["once", "replay"])
    parser.add_argument("--dry-run", action="store_true", help="Show the commands instead of running them")
    parser.add_argument("--fixture", type=Path, help="The rows to replay instead of the live board")
    parser.add_argument("--state", type=Path, default=STATE, help="Where the watcher keeps its state")
    parser.add_argument("--now", type=float, help="The unix time to read the clock at")
    args = parser.parse_args(argv)
    rows = None
    panes = None
    tasks = None
    now = args.now
    if args.action == "replay":
        if args.fixture is None:
            parser.error("replay needs --fixture")
        fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
        rows = fixture.get("rows") if isinstance(fixture, dict) else fixture
        panes = fixture.get("panes") if isinstance(fixture, dict) else None
        tasks = fixture.get("tasks") if isinstance(fixture, dict) else None
        if now is None and isinstance(fixture, dict):
            now = fixture.get("at")
    result = tick(now=now, dry_run=args.dry_run or args.action == "replay", rows=rows, panes=panes,
                  tasks=tasks, state_path=args.state)
    print(json.dumps(result, allow_nan=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(type(error).__name__ + ": " + str(error).splitlines()[0][:240], file=sys.stderr)
        sys.exit(1)
