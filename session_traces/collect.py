"""Read-only collector over ~/.t3/userdata/statev2.sqlite."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .scrub import scrub_path
from .store import day_key, export_posthog, rebuild_day_index, write_trace

DEFAULT_DB = Path.home() / ".t3" / "userdata" / "statev2.sqlite"
TASK_KEY_RE = re.compile(r"\b([A-Z]{2,5}-\d+)\b")
TOOL_TYPES = frozenset(
    {
        "dynamic_tool",
        "command_execution",
        "file_change",
        "file_search",
        "web_search",
        "subagent",
    }
)
PREVIEW_RE = re.compile(
    r"(?i)(preview_|playwright|html_preview|html_render|device_screenshot|"
    r"cursor.?model.?panel|Browser\.|mcp__.*preview)"
)
BLOCKER_RE = re.compile(r"(?i)\b(blocked|blocker|named blocker|waiting on shyam)\b")


def open_db(path: Path | None = None) -> sqlite3.Connection:
    db = Path(path) if path else Path(os.environ.get("T3_STATE_DB", DEFAULT_DB))
    uri = f"file:{db}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        val = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return val if isinstance(val, dict) else {}


def _ms_between(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    try:
        a = datetime.fromisoformat(start.replace("Z", "+00:00"))
        b = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, int((b - a).total_seconds() * 1000))


def _task_key(title: str | None) -> str | None:
    if not title:
        return None
    m = TASK_KEY_RE.search(title)
    return m.group(1) if m else None


def _tokens_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in (
        "inputTokens",
        "outputTokens",
        "totalTokens",
        "cachedInputTokens",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "costUsd",
        "totalCostUsd",
        "cost_usd",
    ):
        if key in payload and payload[key] is not None:
            out[key] = payload[key]
    usage = payload.get("usage")
    if isinstance(usage, dict):
        for key, val in usage.items():
            if any(x in key.lower() for x in ("token", "cost")) and val is not None:
                out[key] = val
    return out


def _tool_name(item_type: str, payload: dict[str, Any]) -> str:
    if item_type == "dynamic_tool":
        return str(payload.get("toolName") or payload.get("title") or "dynamic_tool")
    if item_type == "command_execution":
        title = payload.get("title")
        if title:
            return str(title)
        inp = payload.get("input")
        if isinstance(inp, str) and inp.strip():
            return "shell:" + inp.strip().split()[0][:80]
        return "command_execution"
    if item_type == "file_change":
        return "file_change"
    if item_type == "file_search":
        return str(payload.get("title") or "file_search")
    if item_type == "web_search":
        return "web_search"
    if item_type == "subagent":
        return str(payload.get("title") or "subagent")
    return item_type


def _pr_outcomes(thread_payload: dict[str, Any]) -> list[dict[str, Any]]:
    prs = thread_payload.get("pullRequests") or []
    out = []
    for pr in prs:
        if not isinstance(pr, dict):
            continue
        snap = pr.get("snapshot") if isinstance(pr.get("snapshot"), dict) else {}
        out.append(
            {
                "url": pr.get("url"),
                "repository": pr.get("repository"),
                "number": pr.get("number"),
                "state": snap.get("state") or pr.get("state"),
                "merged_at": snap.get("mergedAt"),
                "merge_sha": snap.get("mergeCommitOid")
                or snap.get("mergeCommit")
                or snap.get("headSha"),
                "checks_state": snap.get("checksState"),
                "review_decision": snap.get("reviewDecision"),
                "head_branch": snap.get("headBranch"),
                "title": snap.get("title"),
            }
        )
    return out


def _named_blocker(
    title: str | None, notifications: list[dict[str, Any]]
) -> str | None:
    if title and BLOCKER_RE.search(title):
        return "title"
    for note in notifications:
        summary = str(note.get("summary") or note.get("title") or "")
        if BLOCKER_RE.search(summary):
            return summary[:120]
    return None


def _allowed_roots(worktree: str | None, workspace: str | None) -> list[str]:
    """Bound worktree, project checkout, and known worktree mirrors for that project."""
    roots: list[str] = []
    for p in (worktree, workspace):
        if p:
            roots.append(str(p))
    if workspace:
        ws = Path(workspace)
        name = ws.name
        home = Path.home()
        for c in (
            home / ".t3" / "worktrees" / name,
            home / ".shepherdr" / "worktrees" / name,
            ws.parent / ".worktrees" / name,
            home / "Code" / ".worktrees" / name,
            home / "Code" / f"{name}-worktrees",
        ):
            roots.append(str(c))
    seen: set[str] = set()
    out: list[str] = []
    for r in roots:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _path_under(path: str, root: str) -> bool:
    try:
        return Path(path).is_relative_to(root)
    except (ValueError, TypeError):
        return path == root or path.startswith(str(root).rstrip("/") + "/")


def collect_runs(
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    db_path: Path | None = None,
    thread_id: str | None = None,
) -> list[dict[str, Any]]:
    """Build one scrubbed-ready trace dict per T3 run in the window."""
    since = since or (datetime.now(timezone.utc) - timedelta(days=1))
    until = until or datetime.now(timezone.utc)
    since_s = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    until_s = until.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.999999")

    conn = open_db(db_path)
    try:
        params: list[Any] = [since_s, until_s]
        thread_clause = ""
        if thread_id:
            thread_clause = " AND r.thread_id = ?"
            params.append(thread_id)
        runs = conn.execute(
            f"""
            SELECT r.run_id, r.thread_id, r.ordinal, r.provider, r.provider_instance_id,
                   r.status, r.requested_at, r.completed_at, r.payload_json AS run_payload,
                   t.title, t.project_id, t.payload_json AS thread_payload,
                   p.title AS project_title, p.workspace_root
            FROM orchestration_v2_projection_runs r
            JOIN orchestration_v2_projection_threads t ON t.thread_id = r.thread_id
            LEFT JOIN projection_projects p ON p.project_id = t.project_id
            WHERE r.requested_at >= ? AND r.requested_at <= ?{thread_clause}
            ORDER BY r.requested_at
            """,
            params,
        ).fetchall()

        traces: list[dict[str, Any]] = []
        for run in runs:
            run_payload = _parse_json(run["run_payload"])
            thread_payload = _parse_json(run["thread_payload"])
            model_sel = run_payload.get("modelSelection") or {}
            model = None
            if isinstance(model_sel, dict):
                model = model_sel.get("model")
            provider = run["provider_instance_id"] or run["provider"]

            items = conn.execute(
                """
                SELECT type, status, ordinal, payload_json, updated_at
                FROM orchestration_v2_projection_turn_items
                WHERE run_id = ?
                ORDER BY ordinal
                """,
                (run["run_id"],),
            ).fetchall()

            tool_calls: list[dict[str, Any]] = []
            touched_files: list[str] = []
            tokens: dict[str, Any] = {}
            notifications: list[dict[str, Any]] = []
            preview_hits: list[str] = []

            for item in items:
                payload = _parse_json(item["payload_json"])
                tokens.update(_tokens_from_payload(payload))
                item_type = item["type"]
                if item_type == "notification":
                    notifications.append(
                        {
                            "summary": payload.get("summary"),
                            "outcome": payload.get("outcome"),
                            "status": payload.get("status"),
                        }
                    )
                if item_type not in TOOL_TYPES:
                    continue
                started = payload.get("startedAt")
                completed = payload.get("completedAt")
                name = _tool_name(item_type, payload)
                entry = {
                    "type": item_type,
                    "name": name,
                    "status": payload.get("status") or item["status"],
                    "started_at": started,
                    "completed_at": completed,
                    "duration_ms": _ms_between(started, completed),
                    "exit_code": payload.get("exitCode"),
                }
                if item_type == "file_change":
                    fname = payload.get("fileName")
                    if fname:
                        touched_files.append(str(fname))
                        entry["file"] = scrub_path(str(fname))
                tool_calls.append(entry)
                if PREVIEW_RE.search(name):
                    preview_hits.append(name)

            worktree = thread_payload.get("worktreePath")
            workspace = run["workspace_root"]
            ok_roots = _allowed_roots(worktree, workspace)
            outside = []
            for path in touched_files:
                if not ok_roots:
                    continue
                if not any(_path_under(path, root) for root in ok_roots):
                    outside.append(scrub_path(path))

            started_at = run_payload.get("startedAt") or run["requested_at"]
            completed_at = run["completed_at"] or run_payload.get("completedAt")
            prs = _pr_outcomes(thread_payload)
            blocker = _named_blocker(run["title"], notifications)

            trace = {
                "schema": "mac-ops.session_trace.v1",
                "run_id": run["run_id"],
                "thread_id": run["thread_id"],
                "ordinal": run["ordinal"],
                "project_id": run["project_id"],
                "project": run["project_title"],
                "task_key": _task_key(run["title"]),
                "title": run["title"],
                "provider": provider,
                "model": model,
                "status": run["status"],
                "requested_at": run["requested_at"],
                "started_at": started_at,
                "completed_at": completed_at,
                "duration_ms": _ms_between(started_at, completed_at),
                "worktree_path": scrub_path(worktree),
                "workspace_root": scrub_path(workspace),
                "branch": thread_payload.get("branch"),
                "tool_calls": tool_calls,
                "tool_call_count": len(tool_calls),
                "tokens": tokens or None,
                "cost_usd": tokens.get("costUsd")
                or tokens.get("totalCostUsd")
                or tokens.get("cost_usd"),
                "pull_requests": prs,
                "named_blocker": blocker,
                "files_outside_worktree": outside,
                "preview_or_playwright": preview_hits,
                "final_state": run["status"],
            }
            traces.append(trace)
        return traces
    finally:
        conn.close()


def collect_and_store(
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    db_path: Path | None = None,
    state_root: Path | None = None,
    export: bool = True,
    dry_run_export: bool = False,
) -> dict[str, Any]:
    traces = collect_runs(since=since, until=until, db_path=db_path)
    paths = []
    days: set[str] = set()
    for trace in traces:
        paths.append(str(write_trace(trace, root=state_root)))
        days.add(day_key(trace.get("started_at") or trace.get("requested_at")))
    for day in days:
        rebuild_day_index(day, root=state_root)
    export_result = {"exported": 0, "skipped": "disabled"}
    if export:
        export_result = export_posthog(traces, dry_run=dry_run_export)
    return {
        "collected": len(traces),
        "days": sorted(days),
        "paths_sample": paths[:5],
        "posthog": export_result,
    }
