#!/usr/bin/python3
"""Pause board agents that are only waiting in the heavy admission queue."""

from __future__ import annotations

import os
import signal
from collections.abc import Callable, Sequence
from typing import Any

STATE_SCHEMA = 1
PAUSE_REASON = "heavy-queue-wait"


def _descendant_pids(root: int, processes: dict[int, Any]) -> set[int]:
    children: dict[int, list[int]] = {}
    for pid, row in processes.items():
        children.setdefault(row.ppid, []).append(pid)
    seen = set()
    pending = [root]
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        pending.extend(children.get(pid, []))
    seen.discard(root)
    return seen


def _cmdline_allows_heavy_wait(cmdline: str) -> bool:
    if not cmdline:
        return True
    lowered = cmdline.lower()
    allowed_fragments = (
        "cursor-agent",
        "cursor_agent_gate",
        "pi_agent_gate",
        "omp_agent_gate",
        "heavy.py",
        "heavy.sh",
        "/heavy",
        " python3 -i ",
    )
    if any(fragment in lowered for fragment in allowed_fragments):
        return True
    first = lowered.split()[0]
    base = os.path.basename(first)
    return base in ("zsh", "bash", "sh", "-zsh", "-bash", "python", "python3")


def _agent_busy(
    process_info: dict[str, Any] | None, supervisor_pids: Sequence[int]
) -> str | None:
    if not isinstance(process_info, dict):
        return "process-info-missing"
    exclude = set(supervisor_pids)
    for pid in supervisor_pids:
        exclude.add(pid)
    foreground = process_info.get("foreground_processes")
    if not isinstance(foreground, list):
        return "foreground-processes-missing"
    for item in foreground:
        if not isinstance(item, dict):
            return "foreground-process-invalid"
        pid = item.get("pid")
        if pid in exclude:
            continue
        cmdline = item.get("cmdline") or item.get("argv0") or ""
        if not _cmdline_allows_heavy_wait(str(cmdline)):
            return "foreground-command"
    return None


def _task_key(task_id: str) -> str:
    return "board:" + task_id


def _queue_supervisor_pids(
    queues: Sequence[dict[str, Any]],
    table: dict[int, Any],
    heavy_mod: Any,
    boot_id: str,
) -> list[int]:
    pids = []
    for row in queues:
        identity = row.get("process")
        if not isinstance(identity, dict):
            continue
        if identity.get("boot_id") != boot_id:
            continue
        pid = identity.get("pid")
        if type(pid) is not int or pid <= 0:
            continue
        if heavy_mod._identity_matches(table.get(pid), identity):
            pids.append(pid)
    return pids


def _active_heavy_task_keys(
    records: Sequence[dict[str, Any]], table: dict[int, Any], heavy_mod: Any
) -> set[str]:
    active = set()
    for record in records:
        state = record.get("state")
        if state in ("complete", "removed"):
            continue
        try:
            alive, supervisor_alive = heavy_mod._record_live(record, table)
        except (AttributeError, KeyError, TypeError, ValueError, OSError):
            alive, supervisor_alive = True, True
        if alive or supervisor_alive:
            task_key = record.get("task_key")
            if isinstance(task_key, str) and task_key:
                active.add(task_key)
    return active


def _pause_targets(
    *,
    agent_census: dict[str, Any],
    admission_active: Sequence[dict[str, Any]],
    queues: Sequence[dict[str, Any]],
    records: Sequence[dict[str, Any]],
    table: dict[int, Any],
    boot_id: str,
    heavy_mod: Any,
) -> dict[str, dict[str, Any]]:
    active_ids = {
        row["id"] for row in admission_active if isinstance(row.get("id"), str)
    }
    queues_by_key: dict[str, list[dict[str, Any]]] = {}
    for row in queues:
        key = row.get("task_key")
        if isinstance(key, str):
            queues_by_key.setdefault(key, []).append(row)
    running_keys = _active_heavy_task_keys(records, table, heavy_mod)
    targets: dict[str, dict[str, Any]] = {}
    for agent in agent_census.get("agents") or []:
        if not isinstance(agent, dict):
            continue
        task_id = agent.get("id")
        if task_id not in active_ids:
            continue
        key = _task_key(task_id)
        task_queues = queues_by_key.get(key, [])
        supervisor_pids = _queue_supervisor_pids(task_queues, table, heavy_mod, boot_id)
        agent_pids = agent.get("pids") or []
        if not isinstance(agent_pids, list) or not all(
            type(pid) is int and pid > 0 for pid in agent_pids
        ):
            eligible = False
            busy = "agent-pids-missing"
            pause_pids: list[int] = []
        elif key in running_keys:
            eligible = False
            busy = "heavy-job-active"
            pause_pids = []
        elif not task_queues:
            eligible = False
            busy = "not-queued"
            pause_pids = []
        elif not supervisor_pids:
            eligible = False
            busy = "queue-supervisor-unverified"
            pause_pids = []
        else:
            excluded = set()
            for supervisor_pid in supervisor_pids:
                excluded.add(supervisor_pid)
                excluded.update(_descendant_pids(supervisor_pid, table))
            pause_pids = sorted({pid for pid in agent_pids if pid not in excluded})
            busy = _agent_busy(agent.get("process_info"), supervisor_pids)
            eligible = busy is None and bool(pause_pids)
        targets[task_id] = {
            "task_key": key,
            "eligible": eligible,
            "busy_reason": busy,
            "pause_pids": pause_pids,
            "supervisor_pids": supervisor_pids,
            "queue_ids": [
                row.get("queue_id")
                for row in task_queues
                if isinstance(row.get("queue_id"), str)
            ],
        }
    return targets


def _signal_pids(
    pids: Sequence[int],
    signum: int,
    *,
    allowed: set[int],
    boot_id: str,
    table: dict[int, Any],
    heavy_mod: Any,
    signal_pid: Callable[[int, int], None],
) -> tuple[list[int], list[int]]:
    ok: list[int] = []
    failed: list[int] = []
    for pid in pids:
        if pid not in allowed:
            failed.append(pid)
            continue
        info = table.get(pid)
        if info is None or info.uid != os.getuid() or info.state.startswith(("Z", "X")):
            failed.append(pid)
            continue
        try:
            signal_pid(pid, signum)
        except OSError:
            failed.append(pid)
            continue
        ok.append(pid)
    return ok, failed


def _empty_state(boot_id: str) -> dict[str, Any]:
    return {"schema": STATE_SCHEMA, "boot_id": boot_id, "paused": {}}


def resume_all(
    state: dict[str, Any] | None,
    *,
    table: dict[int, Any],
    heavy_mod: Any,
    boot_id: str,
    signal_pid: Callable[[int, int], None] = os.kill,
    reason: str = "resume-all",
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(state, dict) or state.get("schema") != STATE_SCHEMA:
        state = _empty_state(boot_id)
    allowed = set()
    for entry in (state.get("paused") or {}).values():
        if isinstance(entry, dict):
            for pid in entry.get("pids") or []:
                if type(pid) is int and pid > 0:
                    allowed.add(pid)
    resumed, failed = _signal_pids(
        sorted(allowed),
        signal.SIGCONT,
        allowed=allowed,
        boot_id=boot_id,
        table=table,
        heavy_mod=heavy_mod,
        signal_pid=signal_pid,
    )
    cleared = _empty_state(boot_id)
    return cleared, {"reason": reason, "resumed": resumed, "failed": failed}


def tick(
    *,
    heavy_mod: Any,
    boot_id: str,
    agent_census: dict[str, Any] | None,
    admission_active: Sequence[dict[str, Any]],
    state: dict[str, Any] | None,
    signal_pid: Callable[[int, int], None] = os.kill,
) -> tuple[dict[str, Any], dict[str, Any]]:
    table = heavy_mod.process_table()
    if not isinstance(state, dict) or state.get("schema") != STATE_SCHEMA:
        state = _empty_state(boot_id)
    if state.get("boot_id") != boot_id:
        state, boot_resume = resume_all(
            state,
            table=table,
            heavy_mod=heavy_mod,
            boot_id=str(state.get("boot_id") or boot_id),
            signal_pid=signal_pid,
            reason="boot-change",
        )
        state = _empty_state(boot_id)
    else:
        boot_resume = None

    if agent_census is None or not agent_census.get("complete"):
        state, resume_info = resume_all(
            state,
            table=table,
            heavy_mod=heavy_mod,
            boot_id=boot_id,
            signal_pid=signal_pid,
            reason="census-incomplete",
        )
        summary = {
            "action": "resume",
            "resume": resume_info,
            "boot_resume": boot_resume,
            "paused_count": 0,
        }
        return state, summary

    registry = heavy_mod.Registry(heavy_mod.state_directory())
    with registry.lock(exclusive=False):
        queues = registry.queue_records()
        records = registry.records()

    targets = _pause_targets(
        agent_census=agent_census,
        admission_active=admission_active,
        queues=queues,
        records=records,
        table=table,
        boot_id=boot_id,
        heavy_mod=heavy_mod,
    )
    paused = dict(state.get("paused") or {})
    resumed_tasks: list[str] = []
    for task_id, entry in list(paused.items()):
        target = targets.get(task_id)
        if target is None or not target.get("eligible"):
            pids = entry.get("pids") if isinstance(entry, dict) else []
            allowed = {pid for pid in pids if type(pid) is int}
            _signal_pids(
                sorted(allowed),
                signal.SIGCONT,
                allowed=allowed,
                boot_id=boot_id,
                table=table,
                heavy_mod=heavy_mod,
                signal_pid=signal_pid,
            )
            paused.pop(task_id, None)
            resumed_tasks.append(task_id)

    paused_tasks: list[str] = []
    pending_tasks: list[str] = []
    for task_id, target in targets.items():
        if not target.get("eligible"):
            continue
        pause_pids = target["pause_pids"]
        existing = paused.get(task_id)
        if (
            isinstance(existing, dict)
            and existing.get("pids") == pause_pids
            and existing.get("status") == "paused"
        ):
            continue
        allowed = set(pause_pids)
        stopped, failed = _signal_pids(
            pause_pids,
            signal.SIGSTOP,
            allowed=allowed,
            boot_id=boot_id,
            table=table,
            heavy_mod=heavy_mod,
            signal_pid=signal_pid,
        )
        if failed and not stopped:
            pending_tasks.append(task_id)
            paused[task_id] = {
                "status": "pause-pending",
                "reason": PAUSE_REASON,
                "pids": pause_pids,
                "queue_ids": target.get("queue_ids"),
            }
            continue
        paused[task_id] = {
            "status": "paused" if not failed else "pause-pending",
            "reason": PAUSE_REASON,
            "pids": pause_pids,
            "queue_ids": target.get("queue_ids"),
            "stopped": stopped,
            "failed": failed,
        }
        paused_tasks.append(task_id)

    state = {"schema": STATE_SCHEMA, "boot_id": boot_id, "paused": paused}
    summary = {
        "action": "tick",
        "boot_resume": boot_resume,
        "resumed_tasks": resumed_tasks,
        "paused_tasks": paused_tasks,
        "pending_tasks": pending_tasks,
        "paused_count": sum(1 for entry in paused.values() if isinstance(entry, dict)),
        "targets": {
            task_id: {
                "eligible": info["eligible"],
                "busy_reason": info.get("busy_reason"),
                "queue_ids": info.get("queue_ids"),
            }
            for task_id, info in targets.items()
        },
    }
    return state, summary
