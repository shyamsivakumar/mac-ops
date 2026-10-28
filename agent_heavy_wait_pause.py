#!/usr/bin/python3
"""Pause board agents that are only waiting in the heavy admission queue."""

from __future__ import annotations

import logging
import signal
from typing import Any

logger = logging.getLogger(__name__)

STATE_SCHEMA = 2
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


def _idle_foreground_cmdline(cmdline: str) -> bool:
    if not cmdline:
        return False
    lowered = cmdline.lower()
    idle_markers = (
        "cursor-agent",
        "cursor_agent_gate",
        "pi_agent_gate",
        "omp_agent_gate",
        "heavy.py",
        "heavy.sh",
        "/.local/bin/heavy",
    )
    return any(marker in lowered for marker in idle_markers)


def _agent_busy(
    process_info: dict[str, Any] | None, supervisor_pids: list[int]
) -> str | None:
    if not isinstance(process_info, dict):
        return "process-info-missing"
    exclude = set(supervisor_pids)
    for pid in supervisor_pids:
        exclude.add(pid)
    foreground = process_info.get("foreground_processes")
    if not isinstance(foreground, list) or not foreground:
        return "foreground-processes-missing"
    saw_idle = False
    for item in foreground:
        if not isinstance(item, dict):
            return "foreground-process-invalid"
        pid = item.get("pid")
        if pid in exclude:
            continue
        cmdline = str(item.get("cmdline") or item.get("argv0") or "")
        if _idle_foreground_cmdline(cmdline):
            saw_idle = True
            continue
        return "foreground-command"
    if not saw_idle:
        return "foreground-not-idle"
    return None


def _task_key(task_id: str) -> str:
    return "board:" + task_id


def _queue_supervisor_pids(
    queues: list[dict[str, Any]],
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
    records: list[dict[str, Any]], table: dict[int, Any], heavy_mod: Any
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


def _pause_identities_for_agent(
    *,
    agent_pids: list[int],
    supervisor_pids: list[int],
    task_key: str,
    boot_id: str,
    table: dict[int, Any],
    heavy_mod: Any,
) -> list[dict[str, Any]]:
    excluded = set()
    for supervisor_pid in supervisor_pids:
        excluded.add(supervisor_pid)
        excluded.update(_descendant_pids(supervisor_pid, table))
    identities = []
    import os

    uid = os.getuid()
    for pid in agent_pids:
        if pid in excluded:
            continue
        identity = heavy_mod._process_pause_identity(pid, task_key, boot_id, table, uid)
        if identity is not None:
            identities.append(identity)
    return identities


def _pause_targets(
    *,
    agent_census: dict[str, Any],
    admission_active: list[dict[str, Any]],
    queues: list[dict[str, Any]],
    records: list[dict[str, Any]],
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
            identities: list[dict[str, Any]] = []
        elif key in running_keys:
            eligible = False
            busy = "heavy-job-active"
            identities = []
        elif not task_queues:
            eligible = False
            busy = "not-queued"
            identities = []
        elif not supervisor_pids:
            eligible = False
            busy = "queue-supervisor-unverified"
            identities = []
        else:
            identities = _pause_identities_for_agent(
                agent_pids=agent_pids,
                supervisor_pids=supervisor_pids,
                task_key=key,
                boot_id=boot_id,
                table=table,
                heavy_mod=heavy_mod,
            )
            busy = _agent_busy(agent.get("process_info"), supervisor_pids)
            eligible = busy is None and bool(identities)
        targets[task_id] = {
            "task_key": key,
            "eligible": eligible,
            "busy_reason": busy,
            "processes": identities,
            "supervisor_pids": supervisor_pids,
            "queue_ids": [
                row.get("queue_id")
                for row in task_queues
                if isinstance(row.get("queue_id"), str)
            ],
        }
    return targets


def _empty_state(boot_id: str) -> dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "boot_id": boot_id,
        "paused": {},
        "resume_pending": [],
    }


def _identity_key(identity: dict[str, Any]) -> tuple[Any, ...]:
    return (
        identity.get("pid"),
        identity.get("start"),
        identity.get("boot_id"),
        identity.get("task_key"),
    )


def _merge_resume_pending(
    existing: list[Any], failed: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    pending = [item for item in existing if isinstance(item, dict)]
    seen = {_identity_key(item) for item in pending}
    for identity in failed:
        key = _identity_key(identity)
        if key not in seen:
            pending.append(identity)
            seen.add(key)
    return pending


def _drop_resumed(
    existing: list[Any], succeeded: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    done = {_identity_key(item) for item in succeeded}
    return [
        item
        for item in existing
        if isinstance(item, dict) and _identity_key(item) not in done
    ]


def resume_all(
    state: dict[str, Any] | None,
    *,
    heavy_mod: Any,
    boot_id: str,
    deps: Any,
    reason: str = "resume-all",
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(state, dict) or state.get("schema") != STATE_SCHEMA:
        state = _empty_state(boot_id)
    identities: list[dict[str, Any]] = []
    for entry in (state.get("paused") or {}).values():
        if isinstance(entry, dict):
            for item in entry.get("processes") or []:
                if isinstance(item, dict):
                    identities.append(item)
    for item in state.get("resume_pending") or []:
        if isinstance(item, dict):
            identities.append(item)
    deduped = []
    seen = set()
    for identity in identities:
        key = _identity_key(identity)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(identity)
    resumed, failed = heavy_mod.signal_verified_processes(deduped, signal.SIGCONT, deps)
    cleared = _empty_state(boot_id)
    if failed:
        cleared["resume_pending"] = _merge_resume_pending([], failed)
    return cleared, {"reason": reason, "resumed": resumed, "failed": failed}


def _sync_queue_agent_pause(
    registry: Any,
    queue_id: str,
    *,
    processes: list[dict[str, Any]],
    status: str,
    requested_ns: int,
) -> None:
    def mutate(row: dict[str, Any]) -> dict[str, Any] | None:
        if row.get("queue_id") != queue_id:
            return None
        updated = dict(row)
        updated["agent_pause"] = {
            "status": status,
            "reason": PAUSE_REASON,
            "requested_ns": requested_ns,
            "processes": processes,
        }
        return updated

    registry.update_queue(queue_id, mutate)


def _clear_queue_agent_pause(registry: Any, queue_id: str) -> None:
    def mutate(row: dict[str, Any]) -> dict[str, Any] | None:
        if row.get("queue_id") != queue_id or not row.get("agent_pause"):
            return None
        updated = dict(row)
        updated.pop("agent_pause", None)
        return updated

    registry.update_queue(queue_id, mutate)


def tick(
    *,
    heavy_mod: Any,
    boot_id: str,
    agent_census: dict[str, Any] | None,
    admission_active: list[dict[str, Any]],
    state: dict[str, Any] | None,
    critical_pressure: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    deps = heavy_mod.SupervisorDeps()
    if not isinstance(state, dict) or state.get("schema") != STATE_SCHEMA:
        state = _empty_state(boot_id)
    resume_pending = [
        item for item in (state.get("resume_pending") or []) if isinstance(item, dict)
    ]
    if state.get("boot_id") != boot_id:
        state, boot_resume = resume_all(
            state,
            heavy_mod=heavy_mod,
            boot_id=str(state.get("boot_id") or boot_id),
            deps=deps,
            reason="boot-change",
        )
        state = _empty_state(boot_id)
        resume_pending = list(state.get("resume_pending") or [])
    else:
        boot_resume = None

    if resume_pending:
        resumed, failed = heavy_mod.signal_verified_processes(
            resume_pending, signal.SIGCONT, deps
        )
        resume_pending = _drop_resumed(resume_pending, resumed)
        resume_pending = _merge_resume_pending(resume_pending, failed)

    if agent_census is None or not agent_census.get("complete"):
        if critical_pressure:
            held = dict(state.get("paused") or {})
            state = {
                "schema": STATE_SCHEMA,
                "boot_id": boot_id,
                "paused": held,
                "resume_pending": resume_pending,
            }
            return state, {
                "action": "hold",
                "reason": "census-incomplete-critical",
                "boot_resume": boot_resume,
                "paused_count": len(held),
            }
        state, resume_info = resume_all(
            state,
            heavy_mod=heavy_mod,
            boot_id=boot_id,
            deps=deps,
            reason="census-incomplete",
        )
        state["resume_pending"] = resume_pending
        return state, {
            "action": "resume",
            "resume": resume_info,
            "boot_resume": boot_resume,
            "paused_count": 0,
        }

    registry = heavy_mod.Registry(heavy_mod.state_directory())
    with registry.lock(exclusive=False):
        queues = registry.queue_records()
        records = registry.records()

    table = heavy_mod.process_table()
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
            processes = entry.get("processes") if isinstance(entry, dict) else []
            if isinstance(processes, list):
                resumed, failed = heavy_mod.signal_verified_processes(
                    processes, signal.SIGCONT, deps
                )
                resume_pending = _merge_resume_pending(
                    _drop_resumed(resume_pending, resumed), failed
                )
            for queue_id in (entry or {}).get("queue_ids") or []:
                if isinstance(queue_id, str):
                    try:
                        _clear_queue_agent_pause(registry, queue_id)
                    except (heavy_mod.HeavyError, OSError) as exc:
                        logger.warning(
                            "could not clear agent pause on queue %s: %s",
                            queue_id,
                            exc,
                        )
            paused.pop(task_id, None)
            resumed_tasks.append(task_id)

    paused_tasks: list[str] = []
    pending_tasks: list[str] = []
    now_ns = deps.monotonic_ns()
    for task_id, target in targets.items():
        if not target.get("eligible"):
            continue
        processes = target["processes"]
        existing = paused.get(task_id)
        if (
            isinstance(existing, dict)
            and existing.get("processes") == processes
            and existing.get("status") == "paused"
        ):
            continue
        stopped, failed = heavy_mod.signal_verified_processes(
            processes, signal.SIGSTOP, deps
        )
        status = "paused" if stopped and not failed else "pause-pending"
        if failed and not stopped:
            pending_tasks.append(task_id)
        else:
            paused_tasks.append(task_id)
        for queue_id in target.get("queue_ids") or []:
            if isinstance(queue_id, str):
                try:
                    _sync_queue_agent_pause(
                        registry,
                        queue_id,
                        processes=processes,
                        status=status,
                        requested_ns=now_ns,
                    )
                except (heavy_mod.HeavyError, OSError) as exc:
                    logger.warning(
                        "could not sync agent pause on queue %s: %s",
                        queue_id,
                        exc,
                    )
        paused[task_id] = {
            "status": status,
            "reason": PAUSE_REASON,
            "processes": processes,
            "queue_ids": target.get("queue_ids"),
            "stopped": stopped,
            "failed": failed,
        }

    state = {
        "schema": STATE_SCHEMA,
        "boot_id": boot_id,
        "paused": paused,
        "resume_pending": resume_pending,
    }
    summary = {
        "action": "tick",
        "boot_resume": boot_resume,
        "resumed_tasks": resumed_tasks,
        "paused_tasks": paused_tasks,
        "pending_tasks": pending_tasks,
        "paused_count": len(paused),
        "resume_pending_count": len(resume_pending),
        "critical_pressure": critical_pressure,
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
