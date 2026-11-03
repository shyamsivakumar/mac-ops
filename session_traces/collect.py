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
from .store import (
    day_key,
    export_posthog,
    load_day_traces,
    rebuild_day_index,
    write_trace,
)

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
NONTERMINAL = frozenset({"queued", "preparing", "starting", "running", "waiting"})


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


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


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
    """Stable tool names only — never persist command text or free-form titles."""
    if item_type == "dynamic_tool":
        name = payload.get("toolName")
        if isinstance(name, str) and name.strip():
            return name.strip()
        return "dynamic_tool"
    if item_type == "command_execution":
        return "command_execution"
    if item_type == "file_change":
        return "file_change"
    if item_type == "file_search":
        return "file_search"
    if item_type == "web_search":
        return "web_search"
    if item_type == "subagent":
        return "subagent"
    return item_type


def _pr_outcomes_for_run(
    thread_payload: dict[str, Any], *, completed_at: str | None, status: str
) -> tuple[list[dict[str, Any]], str]:
    """PR/CI evidence as of the run's end.

    Thread snapshots are current; when merge/check timing cannot be tied to the
    run ending, mark evidence unknown and do not credit a post-run merge.
    """
    prs = thread_payload.get("pullRequests") or []
    out: list[dict[str, Any]] = []
    evidence = "known"
    run_end = _parse_ts(completed_at)
    terminal = status not in NONTERMINAL

    for pr in prs:
        if not isinstance(pr, dict):
            continue
        snap = pr.get("snapshot") if isinstance(pr.get("snapshot"), dict) else {}
        merged_at_raw = snap.get("mergedAt")
        merged_at = _parse_ts(merged_at_raw)
        state = (snap.get("state") or pr.get("state") or "").lower()
        run_merged = False
        timing = "known"

        if merged_at and run_end:
            if merged_at <= run_end:
                run_merged = True
            else:
                # Merged after this run ended — not attributable to the run.
                run_merged = False
                state = "open"
                timing = "post_run_merge"
        elif state == "merged":
            if terminal and run_end is None:
                timing = "unknown"
                evidence = "unknown"
            elif terminal and merged_at is None:
                # State says merged but no timestamp — cannot prove it was merged by run end.
                timing = "unknown"
                evidence = "unknown"
                run_merged = False
                state = "merged_unknown_timing"
            else:
                run_merged = True

        # Merge timing can be known from mergedAt. Checks/review on the thread
        # snapshot are current, not historical — only attach them when the
        # snapshot itself is timestamped at or before run end. Otherwise leave
        # them unknown so a later failing snapshot cannot rewrite earlier runs.
        merge_by_end = run_merged and timing == "known"
        snap_at = _parse_ts(
            snap.get("syncedAt") or snap.get("updatedAt") or snap.get("closedAt")
        )
        ci_by_end = bool(merge_by_end and snap_at and run_end and snap_at <= run_end)
        out.append(
            {
                "url": pr.get("url"),
                "repository": pr.get("repository"),
                "number": pr.get("number"),
                "state": "merged" if run_merged else state,
                "merged_at": merged_at_raw if run_merged else None,
                "merge_sha": (
                    snap.get("mergeCommitOid")
                    or snap.get("mergeCommit")
                    or snap.get("headSha")
                )
                if run_merged
                else None,
                "checks_state": snap.get("checksState") if ci_by_end else None,
                "review_decision": snap.get("reviewDecision") if ci_by_end else None,
                "head_branch": snap.get("headBranch"),
                "title": snap.get("title"),
                "timing": timing,
                "evidence_by_end": ci_by_end,
                "merge_by_end": merge_by_end,
            }
        )
    if not out and terminal:
        evidence = "known"
    return out, evidence


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


def _normalize_path(path: str) -> str:
    return os.path.normpath(path)


def _allowed_roots(worktree: str | None, workspace: str | None) -> list[str]:
    """Only the assigned worktree and the project checkout — never sibling dirs."""
    roots: list[str] = []
    for p in (worktree, workspace):
        if p:
            roots.append(_normalize_path(str(p)))
    seen: set[str] = set()
    out: list[str] = []
    for r in roots:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _path_under(path: str, root: str) -> bool:
    p = Path(_normalize_path(path))
    r = Path(_normalize_path(root))
    try:
        return p.is_relative_to(r)
    except (ValueError, TypeError, AttributeError):
        ps, rs = str(p), str(r)
        return ps == rs or ps.startswith(rs.rstrip("/") + "/")


def collect_runs(
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    db_path: Path | None = None,
    thread_id: str | None = None,
    run_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build one scrubbed-ready trace dict per T3 run in the window."""
    since = since or (datetime.now(timezone.utc) - timedelta(days=1))
    until = until or datetime.now(timezone.utc)
    since_s = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    until_s = until.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.999999")

    conn = open_db(db_path)
    try:
        params: list[Any] = []
        clauses = []
        if run_ids:
            placeholders = ",".join("?" for _ in run_ids)
            clauses.append(f"r.run_id IN ({placeholders})")
            params.extend(run_ids)
        else:
            clauses.append("r.requested_at >= ? AND r.requested_at <= ?")
            params.extend([since_s, until_s])
        if thread_id:
            clauses.append("r.thread_id = ?")
            params.append(thread_id)
        where = " AND ".join(clauses)
        runs = conn.execute(
            f"""
            SELECT r.run_id, r.thread_id, r.ordinal, r.provider, r.provider_instance_id,
                   r.status, r.requested_at, r.completed_at, r.payload_json AS run_payload,
                   t.title, t.project_id, t.payload_json AS thread_payload,
                   p.title AS project_title, p.workspace_root
            FROM orchestration_v2_projection_runs r
            JOIN orchestration_v2_projection_threads t ON t.thread_id = r.thread_id
            LEFT JOIN projection_projects p ON p.project_id = t.project_id
            WHERE {where}
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
                        entry["file"] = scrub_path(_normalize_path(str(fname)))
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
                    outside.append(scrub_path(_normalize_path(path)))

            started_at = run_payload.get("startedAt") or run["requested_at"]
            completed_at = run["completed_at"] or run_payload.get("completedAt")
            prs, outcome_evidence = _pr_outcomes_for_run(
                thread_payload, completed_at=completed_at, status=run["status"]
            )
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
                "outcome_evidence": outcome_evidence,
                "named_blocker": blocker,
                "files_outside_worktree": outside,
                "preview_or_playwright": preview_hits,
                "final_state": run["status"],
            }
            traces.append(trace)
        return traces
    finally:
        conn.close()


def _unfinished_run_ids(root: Path | None, lookback_days: int = 3) -> list[str]:
    """Stored traces still non-terminal — refresh on the next daily pass."""
    ids: list[str] = []
    today = datetime.now().astimezone().date()
    for i in range(lookback_days + 1):
        day = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        for trace in load_day_traces(day, root=root):
            status = (trace.get("status") or "").lower()
            if status in NONTERMINAL and trace.get("run_id"):
                ids.append(str(trace["run_id"]))
    return ids


def collect_and_store(
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    db_path: Path | None = None,
    state_root: Path | None = None,
    export: bool = True,
    dry_run_export: bool = False,
    reconcile_unfinished: bool = True,
) -> dict[str, Any]:
    traces = collect_runs(since=since, until=until, db_path=db_path)
    refreshed = 0
    if reconcile_unfinished:
        unfinished = _unfinished_run_ids(state_root)
        # Avoid double-collecting runs already in this window.
        have = {t["run_id"] for t in traces}
        missing = [rid for rid in unfinished if rid not in have]
        if missing:
            extra = collect_runs(db_path=db_path, run_ids=missing)
            traces.extend(extra)
            refreshed = len(extra)
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
        "reconciled_unfinished": refreshed,
        "days": sorted(days),
        "paths_sample": paths[:5],
        "posthog": export_result,
    }
