"""Read-only collector over T3 Code threads, read through ``t3mcp``.

The T3 server owns the threads and the runs, so ``t3_thread_list`` and
``t3_thread_read`` are the only sources this collector reads. It never calls a
T3 write tool.

What is read
------------
* ``t3_thread_list`` (``includeSubagents`` false) — thread rows: ids, title,
  project, status, update time, linked pull requests.
* ``t3_thread_read`` — ``recentRuns``: run id, ordinal, status, requested and
  executed model, start and end times; and, for review threads only, the
  assistant messages that carry the final ``VERDICT: PASS``/``VERDICT: FAIL``.

What is stored
--------------
Whitelisted metadata only: ids, task key, model/provider, timings, PR state as
T3 reports it, and the final verdict word of a review's last report together
with the review's model, thread id and time. No prompt, command text, tool
output, diff, secret or e-mail is ever copied into a trace.

Fields T3 does not supply (tool calls, token and cost numbers, stop reason,
task type, worktree, merge times, check state) stay ``None``: they are not
collected. An unknown review verdict is never guessed and a merge is never
credited to a run when its timing cannot be shown.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from collections.abc import Callable

from .store import (
    day_key,
    export_posthog,
    load_day_traces,
    rebuild_day_index,
    write_trace,
)

T3MCP = "t3mcp"
T3_TIMEOUT_SECONDS = 120
LIST_PAGE_LIMIT = 100
MESSAGE_PAGE_LIMIT = 100
MAX_PAGES = 200
RECONCILE_LOOKBACK = timedelta(days=7)

TASK_KEY_RE = re.compile(r"\b([A-Z]{2,5}-\d+)\b")
BLOCKER_RE = re.compile(r"(?i)\b(blocked|blocker|named blocker|waiting on shyam)\b")
NONTERMINAL = frozenset({"queued", "preparing", "starting", "running", "waiting"})
VERDICT_LINE_RE = re.compile(r"VERDICT: (PASS|FAIL)")

T3Call = Callable[[str, dict[str, Any]], Any]


def _t3_call(tool: str, args: dict[str, Any]) -> Any:
    result = subprocess.run(
        [T3MCP, "call", tool, json.dumps(args)],
        capture_output=True,
        text=True,
        timeout=T3_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"t3mcp {tool} failed: {result.stderr.strip()[:200]}")
    return json.loads(result.stdout)


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


def _named_blocker(title: str | None) -> str | None:
    return "title" if title and BLOCKER_RE.search(title) else None


def _model_family(model: str | None) -> str | None:
    """Provider-neutral model name: ``subscriptions/gpt-6.1-terra`` -> ``gpt-6.1-terra``."""
    return model.rsplit("/", 1)[-1] if model else None


def _clean_model(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _verdict_word(text: str | None) -> str | None:
    """The final ``VERDICT: PASS``/``VERDICT: FAIL`` line: the word only."""
    if not text:
        return None
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return None
    m = VERDICT_LINE_RE.fullmatch(lines[-1])
    return m.group(1) if m else None


def _is_review_thread(thread: dict[str, Any]) -> bool:
    return "review" in str(thread.get("title") or "").lower()


def _review_origin_ok(thread: dict[str, Any]) -> bool:
    """A review counts only when the coordinator launched it on its own."""
    return not (thread.get("parentThreadId") or thread.get("relationshipToParent"))


def _list_threads(call: T3Call, since: datetime) -> list[dict[str, Any]]:
    """Thread rows updated at or after ``since``; the list is newest-updated first."""
    rows: list[dict[str, Any]] = []
    cursor = 0
    for _ in range(MAX_PAGES):
        page = call(
            "t3_thread_list",
            {
                "allProjects": True,
                "includeSubagents": False,
                "limit": LIST_PAGE_LIMIT,
                "cursor": cursor,
            },
        )
        page_rows = page.get("threads") or []
        stale = False
        for row in page_rows:
            updated = _parse_ts(row.get("updatedAt"))
            if updated is not None and updated < since:
                stale = True
                continue
            rows.append(row)
        next_cursor = page.get("nextCursor")
        if stale or next_cursor is None or not page_rows:
            break
        cursor = next_cursor
    return rows


def _messages(
    call: T3Call, thread_id: str, cache: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The thread record, its recent runs and its user and assistant messages."""
    if thread_id in cache:
        return cache[thread_id]
    items: list[dict[str, Any]] = []
    read: dict[str, Any] = {}
    after = 0
    for _ in range(MAX_PAGES):
        read = call(
            "t3_thread_read",
            {
                "threadId": thread_id,
                "view": "messages",
                "limit": MESSAGE_PAGE_LIMIT,
                "runLimit": 50,
                "afterPosition": after,
            },
        )
        items.extend(read.get("items") or [])
        if not read.get("hasMore"):
            break
        after = read["nextPosition"]
    cache[thread_id] = (read, items)
    return read, items


def _thread_prs(thread: dict[str, Any]) -> list[dict[str, Any]]:
    prs: list[dict[str, Any]] = []
    seen: set[tuple[str | None, Any]] = set()
    raw = list(thread.get("pullRequests") or [])
    linked = thread.get("linkedPullRequest")
    if isinstance(linked, dict):
        raw.append(linked)
    for pr in raw:
        if not isinstance(pr, dict):
            continue
        repo = pr.get("repository")
        number = pr.get("number")
        key = (str(repo) if repo else None, number)
        if key in seen:
            continue
        seen.add(key)
        prs.append(
            {
                "repository": repo,
                "number": number,
                "url": pr.get("url"),
                "state": (pr.get("state") or "").lower() or None,
            }
        )
    return prs


def _pr_evidence(
    thread: dict[str, Any], *, status: str
) -> tuple[list[dict[str, Any]], str]:
    """PR state T3 reports. T3 gives no merge time, so a merged PR has unknown timing."""
    terminal = status not in NONTERMINAL
    out: list[dict[str, Any]] = []
    evidence = "known"
    for pr in _thread_prs(thread):
        state = pr.get("state")
        timing = "known"
        if state == "merged":
            state = "merged_unknown_timing"
            timing = "unknown"
            if terminal:
                evidence = "unknown"
        out.append(
            {
                "url": pr.get("url"),
                "repository": pr.get("repository"),
                "number": pr.get("number"),
                "state": state,
                "merged_at": None,
                "merge_sha": None,
                "checks_state": None,
                "review_decision": None,
                "head_branch": None,
                "timing": timing,
                "evidence_by_end": False,
                "merge_by_end": False,
            }
        )
    return out, evidence


def _final_report_verdict(
    run: dict[str, Any], items: list[dict[str, Any]]
) -> str | None:
    """PASS or FAIL when every assistant report after the run's last user message agrees."""
    if str(run.get("status") or "").lower() != "completed":
        return None
    run_items = [i for i in items if i.get("runId") == run.get("runId")]
    last_user = max(
        (n for n, i in enumerate(run_items) if i.get("type") == "user_message"),
        default=-1,
    )
    reports = [
        i for i in run_items[last_user + 1 :] if i.get("type") == "assistant_message"
    ]
    words = {_verdict_word(r.get("text")) for r in reports}
    only = words.pop() if len(words) == 1 else None
    return only if only in ("PASS", "FAIL") else None


def _find_review(
    thread: dict[str, Any], rows: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """The review thread that gates this task: same project, same ticket."""
    task_key = _task_key(thread.get("title"))
    if not task_key:
        return None
    key_re = re.compile(rf"\b{re.escape(task_key)}\b")
    candidates = [
        other
        for other in rows
        if other.get("threadId") != thread.get("threadId")
        and other.get("projectId") == thread.get("projectId")
        and not other.get("archived")
        and key_re.search(str(other.get("title") or ""))
        and _is_review_thread(other)
        and _review_origin_ok(other)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda row: str(row.get("updatedAt") or ""))


def _review_evidence(
    call: T3Call,
    thread: dict[str, Any],
    rows: list[dict[str, Any]],
    current_run: dict[str, Any],
    cache: dict[str, Any],
) -> dict[str, Any]:
    """Verdict word plus the review's model, thread id and time: nothing else."""
    out: dict[str, Any] = {
        "review_verdict": None,
        "review_model": None,
        "review_thread_id": None,
        "review_run_id": None,
        "review_completed_at": None,
    }
    if _is_review_thread(thread):
        review = thread
    else:
        review = _find_review(thread, rows)
    if review is None:
        return out
    read, items = _messages(call, str(review["threadId"]), cache)
    if _is_review_thread(thread):
        run = current_run
    else:
        runs = read.get("recentRuns") or []
        run = runs[-1] if runs else None
    if not isinstance(run, dict):
        return out
    out["review_verdict"] = _final_report_verdict(run, items)
    out["review_model"] = _clean_model(run.get("executedModel")) or _clean_model(
        run.get("model")
    )
    out["review_thread_id"] = review.get("threadId")
    out["review_run_id"] = run.get("runId")
    out["review_completed_at"] = run.get("completedAt")
    return out


def collect_runs(
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    t3_call: T3Call | None = None,
    thread_id: str | None = None,
    run_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build one scrubbed-ready trace dict per T3 run in the window."""
    call = t3_call or _t3_call
    now = datetime.now(timezone.utc)
    since = since or (now - timedelta(days=1))
    until = until or now
    since_dt = since.astimezone(timezone.utc)
    until_dt = until.astimezone(timezone.utc)
    wanted = set(run_ids) if run_ids else None
    list_since = now - RECONCILE_LOOKBACK if wanted is not None else since_dt

    rows = _list_threads(call, list_since)
    message_cache: dict[str, Any] = {}
    traces: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda r: str(r.get("createdAt") or "")):
        tid = str(row.get("threadId") or "")
        if thread_id and tid != thread_id:
            continue
        read = call("t3_thread_read", {"threadId": tid, "limit": 1, "runLimit": 50})
        thread = {**row, **(read.get("thread") or {})}
        runs = read.get("recentRuns") or []
        title = str(thread.get("title") or "")
        project_id = thread.get("projectId")

        for run in runs:
            if not isinstance(run, dict):
                continue
            run_id = str(run.get("runId") or "")
            started_at = (
                run.get("startedAt")
                or run.get("requestedAt")
                or thread.get("createdAt")
            )
            completed_at = run.get("completedAt")
            if wanted is not None:
                if run_id not in wanted:
                    continue
            else:
                start_dt = _parse_ts(started_at)
                if start_dt is None or start_dt < since_dt or start_dt >= until_dt:
                    continue

            status = str(run.get("status") or "")
            requested = _clean_model(run.get("model"))
            actual = _clean_model(run.get("executedModel")) or requested
            fell_back = bool(
                actual
                and requested
                and _model_family(actual) != _model_family(requested)
            )
            prs, outcome_evidence = _pr_evidence(thread, status=status)
            review = _review_evidence(call, thread, rows, run, message_cache)
            run_end = _parse_ts(completed_at)
            review_completed = _parse_ts(review.get("review_completed_at"))

            traces.append(
                {
                    "schema": "mac-ops.session_trace.v1",
                    "source": "t3",
                    "run_id": run_id,
                    "thread_id": tid,
                    "ordinal": run.get("ordinal"),
                    "project_id": project_id,
                    "project": project_id,
                    "task_key": _task_key(title),
                    "task_type": None,
                    "title": None,
                    "provider": run.get("providerInstanceId")
                    or thread.get("providerInstanceId"),
                    "model": actual,
                    "requested_model": requested,
                    "status": status,
                    "stop_reason": None,
                    "requested_at": run.get("requestedAt") or started_at,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "duration_ms": _ms_between(started_at, completed_at),
                    "worktree_path": None,
                    "workspace_root": None,
                    "branch": None,
                    "tool_calls": None,
                    "tool_call_count": None,
                    "tokens": None,
                    "cost_usd": None,
                    "pull_requests": prs,
                    "outcome_evidence": outcome_evidence,
                    "named_blocker": _named_blocker(title),
                    "files_outside_worktree": [],
                    "preview_or_playwright": [],
                    "final_state": status,
                    "review_verdict": review.get("review_verdict"),
                    "review_model": review.get("review_model"),
                    "review_thread_id": review.get("review_thread_id"),
                    "review_run_id": review.get("review_run_id"),
                    "review_completed_at": review.get("review_completed_at"),
                    "review_evidence_by_end": bool(
                        review_completed is not None
                        and run_end is not None
                        and review_completed <= run_end
                    ),
                    "model_fallback": fell_back,
                    "fallback_model": actual if fell_back else None,
                    "base_model": requested if fell_back else None,
                }
            )
    return traces


def _unfinished_run_ids(root: Path | None, lookback_days: int = 3) -> list[str]:
    """Stored traces still non-terminal: refresh on the next daily pass."""
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
    t3_call: T3Call | None = None,
    state_root: Path | None = None,
    export: bool = True,
    dry_run_export: bool = False,
    reconcile_unfinished: bool = True,
) -> dict[str, Any]:
    traces = collect_runs(since=since, until=until, t3_call=t3_call)
    refreshed = 0
    if reconcile_unfinished:
        unfinished = _unfinished_run_ids(state_root)
        have = {t["run_id"] for t in traces}
        missing = [rid for rid in unfinished if rid not in have]
        if missing:
            extra = collect_runs(t3_call=t3_call, run_ids=missing)
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
