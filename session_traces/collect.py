"""Read-only collector over the Empryo hub state directory (``~/.empryo-hub``).

MO-152 replaces the old T3 SQLite source.  The hub owns the threads, the runs
and the transcripts, so the hub is the only place this collector reads.

What is read
------------
* ``threads.json``  — thread and run metadata (ids, model, status, times, PRs).
* ``hub.log``      — merge events.
* ``transcripts/`` — the per-thread item log, used for tool counts only.

What is stored
--------------
Whitelisted metadata only: ids, task key, model/provider, timings, tool
counts, token and cost numbers, PR state the hub logged as merged, and the
final ``VERDICT: PASS``/``VERDICT: FAIL`` word of a review's last report
together with the review's model, thread id and time.  No prompt, command
text, tool output, diff, secret or e-mail is ever copied into a trace.

Where there is no evidence the field stays empty or ``None`` — an unknown
review verdict is never guessed and a merge is never credited to a run that
ended before it happened.

The hub is never executed: no socket call, no ``emp-hub`` invocation.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .store import (
    day_key,
    export_posthog,
    load_day_traces,
    rebuild_day_index,
    write_trace,
)

DEFAULT_HUB = Path.home() / ".empryo-hub"
LOCAL_TZ = ZoneInfo("America/Los_Angeles")

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
BLOCKER_RE = re.compile(r"(?i)\b(blocked|blocker|named blocker|waiting on shyam)\b")
NONTERMINAL = frozenset({"queued", "preparing", "starting", "running", "waiting"})

VERDICT_LINE_RE = re.compile(r"VERDICT: (PASS|FAIL)")
HUB_LOG_TS_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(?P<rest>.*)$")
HUB_MERGE_RE = re.compile(
    r"^merged (?P<repo>[^#\s]+)#(?P<number>\d+) \((?P<method>[^)]*)\) for (?P<thread>\S+)$"
)
TOOL_KIND_RE = re.compile(r"^[a-z_]{1,20}$")


# --------------------------------------------------------------------------
# small shared helpers (kept import-stable for the legacy eval tests)
# --------------------------------------------------------------------------




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








# --------------------------------------------------------------------------
# hub readers (read-only; the hub itself is never executed)
# --------------------------------------------------------------------------


def _hub_root(hub_path: Path | None = None) -> Path:
    if hub_path:
        return Path(hub_path).expanduser()
    env = os.environ.get("EMPRYO_HUB_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    return DEFAULT_HUB


def _load_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_threads(hub_root: Path) -> dict[str, dict[str, Any]]:
    data = _load_json_file(hub_root / "threads.json")
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, val in data.items():
        if isinstance(val, dict):
            out[str(key)] = val
    return out


def _load_projects(hub_root: Path) -> dict[str, dict[str, Any]]:
    data = _load_json_file(hub_root / "projects.json")
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}


def _hub_log_ts(raw: str) -> str | None:
    """Hub log stamps are local wall-clock; normalize them to UTC ISO."""
    try:
        local = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=LOCAL_TZ)
    except ValueError:
        return None
    return local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_hub_log(path: Path) -> dict[str, Any]:
    """Pull merge events out of hub.log (run models come from threads.json)."""
    merges: list[dict[str, Any]] = []
    try:
        handle = path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return {"merges": merges}
    with handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            m = HUB_LOG_TS_RE.match(line)
            if not m:
                continue
            ts = _hub_log_ts(m.group("ts"))
            rest = m.group("rest").strip()
            merge = HUB_MERGE_RE.match(rest)
            if merge:
                merges.append(
                    {
                        "merged_at": ts,
                        "repository": merge.group("repo"),
                        "number": int(merge.group("number")),
                        "method": merge.group("method"),
                        "thread_id": merge.group("thread"),
                    }
                )
                continue
    return {"merges": merges}


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "thread"


def _transcript_path(hub_root: Path, thread_id: str) -> Path:
    return (
        hub_root
        / "transcripts"
        / f"{_slugify(thread_id)}-{thread_id.split(':')[-1][:8]}.jsonl"
    )


def _read_items(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    try:
        handle = path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return items
    with handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                items.append(obj)
    return items


def _split_run_items(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Split a transcript into per-run segments (a run ends at run_finished)."""
    segments: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for item in items:
        current.append(item)
        if item.get("type") == "run_finished":
            segments.append(current)
            current = []
    if current:
        segments.append(current)
    return segments


def _tool_calls_from_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tool counts and timings only — never the tool title or its output."""
    calls: list[dict[str, Any]] = []
    for item in items:
        item_type = item.get("type")
        if item_type not in TOOL_TYPES:
            continue
        entry: dict[str, Any] = {
            "type": item_type,
            "name": item_type,
            "status": item.get("status"),
            "started_at": item.get("createdAt"),
            "completed_at": None,
            "duration_ms": None,
        }
        kind = item.get("toolKind")
        if isinstance(kind, str) and TOOL_KIND_RE.match(kind):
            entry["tool_kind"] = kind
        calls.append(entry)
    return calls


def _trailing_reports(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assistant reports that trail the last run (hub's own gate rule)."""
    reports: list[dict[str, Any]] = []
    for item in reversed(items):
        if item.get("type") == "assistant_message":
            reports.append(item)
        elif item.get("type") not in ("run_finished", "notice", "error"):
            break
    return list(reversed(reports))


def _verdict_word(text: str | None) -> str | None:
    """The final ``VERDICT: PASS``/``VERDICT: FAIL`` line — the word only."""
    if not text:
        return None
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return None
    m = VERDICT_LINE_RE.fullmatch(lines[-1])
    return m.group(1) if m else None


def _is_review_thread(thread: dict[str, Any]) -> bool:
    return "review" in str(thread.get("title") or "").lower()


def _review_origin_ok(thread: dict[str, Any], items: list[dict[str, Any]]) -> bool:
    """A review counts only when the coordinator launched it on its own."""
    if thread.get("launchedByThread"):
        return False
    if thread.get("parentThreadId") or thread.get("relationshipToParent"):
        return False
    for item in items:
        if item.get("type") == "user_message" and item.get("senderThreadId"):
            return False
    return True


# --------------------------------------------------------------------------
# collection
# --------------------------------------------------------------------------


def _run_model(run: dict[str, Any]) -> str | None:
    """The model the run actually used, from the run record itself."""
    model = run.get("model")
    return model.strip() if isinstance(model, str) and model.strip() else None


def _model_family(model: str | None) -> str | None:
    """Provider-neutral model name: ``subscriptions/gpt-6.1-terra`` -> ``gpt-6.1-terra``."""
    return model.rsplit("/", 1)[-1] if model else None


def _requested_model(thread: dict[str, Any]) -> str | None:
    selection = thread.get("modelSelection")
    model = selection.get("model") if isinstance(selection, dict) else None
    model = model or thread.get("model")
    return model.strip() if isinstance(model, str) and model.strip() else None


def _usage_fields(run: dict[str, Any]) -> tuple[dict[str, Any], float | None]:
    usage = run.get("usage")
    tokens: dict[str, Any] = {}
    cost: float | None = None
    if not isinstance(usage, dict):
        return tokens, cost
    raw = usage.get("tokens")
    if isinstance(raw, dict):
        mapping = {
            "input": "inputTokens",
            "output": "outputTokens",
            "cachedRead": "cachedInputTokens",
            "cachedWrite": "cachedWriteTokens",
        }
        for src, dst in mapping.items():
            val = raw.get(src)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                tokens[dst] = val
        if "inputTokens" in tokens and "outputTokens" in tokens:
            tokens["totalTokens"] = tokens["inputTokens"] + tokens["outputTokens"]
    steps = usage.get("steps")
    if isinstance(steps, int) and not isinstance(steps, bool):
        tokens["steps"] = steps
    val = usage.get("costUsd")
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        cost = float(val)
    return tokens, cost


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


def _merge_events_for(
    pr: dict[str, Any], merges: list[dict[str, Any]], thread_id: str
) -> list[dict[str, Any]]:
    repo = pr.get("repository")
    number = pr.get("number")
    out = []
    for merge in merges:
        if merge.get("thread_id") != thread_id:
            continue
        if repo and merge.get("repository") != repo:
            continue
        if number is not None and merge.get("number") != number:
            continue
        out.append(merge)
    return out


def _pr_evidence(
    thread: dict[str, Any],
    *,
    completed_at: str | None,
    status: str,
    merges: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    """PR state the hub actually logged.

    Only a merge the hub logged, for this thread, at or before the run ended
    is credited.  Check and review state are not available locally, so they
    stay ``None`` rather than being guessed from a current snapshot.
    """
    run_end = _parse_ts(completed_at)
    terminal = status not in NONTERMINAL
    out: list[dict[str, Any]] = []
    evidence = "known"

    for pr in _thread_prs(thread):
        events = _merge_events_for(pr, merges, str(thread.get("threadId") or ""))
        merged_at_raw: str | None = None
        merged_at: datetime | None = None
        for event in events:
            stamp = event.get("merged_at")
            parsed = _parse_ts(stamp)
            if parsed is None:
                continue
            if merged_at is None or parsed < merged_at:
                merged_at = parsed
                merged_at_raw = stamp

        state = pr.get("state")
        timing = "known"
        merge_by_end = False
        if merged_at is not None and run_end is not None:
            if merged_at <= run_end:
                merge_by_end = True
                state = "merged"
            else:
                # Merged after this run ended — not attributable to the run.
                state = "open"
                timing = "post_run_merge"
                merged_at_raw = None
        elif state == "merged":
            # The hub says merged but there is no logged merge time for this
            # thread, so the timing cannot be proven.
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
                "merged_at": merged_at_raw if merge_by_end else None,
                "merge_sha": None,
                "checks_state": None,
                "review_decision": None,
                "head_branch": None,
                "timing": timing,
                "evidence_by_end": False,
                "merge_by_end": merge_by_end,
            }
        )
    return out, evidence


def _find_review(
    thread: dict[str, Any],
    threads: dict[str, dict[str, Any]],
    items_of,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """The review thread that gates this task: same project, same ticket."""
    task_key = _task_key(thread.get("title"))
    if not task_key:
        return None, []
    key_re = re.compile(rf"\b{re.escape(task_key)}\b")
    candidates = []
    for other in threads.values():
        if other.get("threadId") == thread.get("threadId"):
            continue
        if other.get("projectId") != thread.get("projectId"):
            continue
        if other.get("archived"):
            continue
        title = str(other.get("title") or "")
        if not key_re.search(title):
            continue
        if not _is_review_thread(other):
            continue
        candidates.append(other)
    ok = []
    for cand in candidates:
        items = items_of(cand)
        if _review_origin_ok(cand, items):
            ok.append((cand, items))
    if not ok:
        return None, []
    ok.sort(key=lambda pair: str(pair[0].get("updatedAt") or ""))
    cand, items = ok[-1]
    return cand, items


def _review_evidence(
    thread: dict[str, Any],
    threads: dict[str, dict[str, Any]],
    items_of,
    current_run: dict[str, Any],
) -> dict[str, Any]:
    """Verdict word plus the review's model, thread id and time — nothing else."""
    out: dict[str, Any] = {
        "review_verdict": None,
        "review_model": None,
        "review_thread_id": None,
        "review_run_id": None,
        "review_completed_at": None,
    }
    if _is_review_thread(thread):
        review, items = thread, items_of(thread)
    else:
        review, items = _find_review(thread, threads, items_of)
    if review is None:
        return out

    runs = review.get("runs") or []
    run = current_run if _is_review_thread(thread) else (runs[-1] if runs else None)
    if not isinstance(run, dict):
        return out

    verdict: str | None = None
    if str(run.get("status") or "").lower() == "completed":
        segments = _split_run_items(items)
        ordinal = run.get("ordinal")
        segment = segments[ordinal - 1] if isinstance(ordinal, int) and 1 <= ordinal <= len(segments) and segments[ordinal - 1][-1].get("type") == "run_finished" else []
        reports = _trailing_reports(segment)
        words = {_verdict_word(r.get("text")) for r in reports}
        if len(words) == 1:
            only = words.pop()
            if only in ("PASS", "FAIL"):
                verdict = only

    out["review_verdict"] = verdict
    out["review_model"] = _run_model(run)
    out["review_thread_id"] = review.get("threadId")
    out["review_run_id"] = run.get("runId")
    out["review_completed_at"] = run.get("completedAt")
    return out


def collect_runs(
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    hub_path: Path | None = None,
    thread_id: str | None = None,
    run_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build one scrubbed-ready trace dict per hub run in the window."""
    hub_root = _hub_root(hub_path)
    since = since or (datetime.now(timezone.utc) - timedelta(days=1))
    until = until or datetime.now(timezone.utc)
    since_dt = since.astimezone(timezone.utc)
    until_dt = until.astimezone(timezone.utc)

    threads = _load_threads(hub_root)
    projects = _load_projects(hub_root)
    log = _parse_hub_log(hub_root / "hub.log")
    merges = log["merges"]

    items_cache: dict[str, list[dict[str, Any]]] = {}

    def items_of(thread: dict[str, Any]) -> list[dict[str, Any]]:
        tid = str(thread.get("threadId") or "")
        if tid not in items_cache:
            items_cache[tid] = _read_items(_transcript_path(hub_root, tid))
        return items_cache[tid]

    wanted = set(run_ids) if run_ids else None

    traces: list[dict[str, Any]] = []
    for tid, thread in sorted(threads.items(), key=lambda kv: str(kv[1].get("createdAt") or "")):
        if thread_id and tid != thread_id:
            continue
        runs = thread.get("runs") or []
        if not isinstance(runs, list):
            continue
        segments = _split_run_items(items_of(thread))
        project_id = thread.get("projectId")
        project = projects.get(str(project_id)) or {}
        title = str(thread.get("title") or "")
        task_key = _task_key(title)
        worktree = thread.get("worktreePath")
        workspace = project.get("workspaceRoot")
        provider = thread.get("providerInstanceId")
        blocker = _named_blocker(title, [])

        for index, run in enumerate(runs):
            if not isinstance(run, dict):
                continue
            run_id = str(run.get("runId") or "")
            started_at = run.get("startedAt") or thread.get("createdAt")
            completed_at = run.get("completedAt")
            if wanted is not None:
                if run_id not in wanted:
                    continue
            else:
                start_dt = _parse_ts(started_at)
                if start_dt is None:
                    continue
                if start_dt < since_dt or start_dt >= until_dt:
                    continue

            status = str(run.get("status") or "")
            items = segments[index] if index < len(segments) else []
            tool_calls = _tool_calls_from_items(items)
            tokens, cost = _usage_fields(run)
            prs, outcome_evidence = _pr_evidence(
                thread,
                completed_at=completed_at,
                status=status,
                merges=merges,
            )
            review = _review_evidence(thread, threads, items_of, run)
            run_end = _parse_ts(completed_at)
            actual = _run_model(run)
            requested = _requested_model(thread)
            fell_back = bool(actual and requested and _model_family(actual) != _model_family(requested))
            review_completed = _parse_ts(review.get("review_completed_at"))

            trace = {
                "schema": "mac-ops.session_trace.v1",
                "source": "empryo-hub",
                "run_id": run_id,
                "thread_id": tid,
                "ordinal": run.get("ordinal"),
                "project_id": project_id,
                "project": project_id,
                "task_key": task_key,
                "task_type": thread.get("taskType") if thread.get("taskType") in {"standard", "review", "risky", "chore", "design", "rca", "large", "research", "ui", "panel"} else None,
                "title": None,
                "provider": provider,
                "model": actual,
                "requested_model": requested,
                "status": status,
                "stop_reason": run.get("stopReason") if run.get("stopReason") in {"end_turn", "cancelled", "error", "max_turns", "interrupted", "turn_budget"} else None,
                "requested_at": started_at,
                "started_at": started_at,
                "completed_at": completed_at,
                "duration_ms": _ms_between(started_at, completed_at),
                "worktree_path": None,
                "workspace_root": None,
                "branch": None,
                "tool_calls": tool_calls,
                "tool_call_count": len(tool_calls),
                "tokens": tokens or None,
                "cost_usd": cost,
                "pull_requests": prs,
                "outcome_evidence": outcome_evidence,
                "named_blocker": blocker,
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
            traces.append(trace)
    return traces


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
    hub_path: Path | None = None,
    state_root: Path | None = None,
    export: bool = True,
    dry_run_export: bool = False,
    reconcile_unfinished: bool = True,
) -> dict[str, Any]:
    traces = collect_runs(since=since, until=until, hub_path=hub_path)
    refreshed = 0
    if reconcile_unfinished:
        unfinished = _unfinished_run_ids(state_root)
        # Avoid double-collecting runs already in this window.
        have = {t["run_id"] for t in traces}
        missing = [rid for rid in unfinished if rid not in have]
        if missing:
            extra = collect_runs(hub_path=hub_path, run_ids=missing)
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
