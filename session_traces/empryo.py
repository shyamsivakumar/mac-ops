"""Read Empryo's local journal without retaining conversational content."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = Path.home() / ".empryo" / "threads.db"
TOOLS = frozenset("shell code_script read run_tool final_response ast_edit grep project edit_file git shell_jobs navigate genome_impact tool_search multi_edit find show refactor link".split())


def _id(value: Any) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 512:
        return None
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        return None
    return hashlib.sha256(encoded).hexdigest()


def _timestamp(value: Any) -> str:
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def collect_empryo(*, since: datetime | None = None, until: datetime | None = None,
                   run_ids: list[str] | None = None,
                   thread_ids: dict[str, str | None] | None = None) -> list[dict[str, Any]]:
    db = Path(os.environ.get("EMPRYO_THREADS_DB", DEFAULT_DB))
    if not db.is_file():
        return []
    since = since or datetime.now(timezone.utc) - timedelta(days=1)
    until = until or datetime.now(timezone.utc)
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        rows = conn.execute("SELECT id, session_dir FROM threads").fetchall()
    # Import lazily: collect.py imports this module.
    from .collect import PREVIEW_RE, TASK_KEY_RE
    from .scrub import safe_model_id
    traces: dict[str, dict[str, Any]] = {}
    remaining = set(run_ids) if run_ids is not None else None
    for thread, directory in rows:
        if remaining is not None and not remaining:
            break
        thread_hash = _id(thread)
        if not thread_hash or not isinstance(directory, str) or not directory:
            continue
        if remaining is not None and thread_ids is not None:
            journal_thread = "empryo-" + thread_hash
            if not any(not thread_ids.get(rid) or thread_ids[rid] == journal_thread
                       for rid in remaining):
                continue
        folder = Path(directory)
        try:
            meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
            if not isinstance(meta, dict) or meta.get("id") != thread:
                continue
            # A session cannot contain turns before its creation. Missing or
            # invalid metadata is not a reason to exclude a journal.
            started = meta.get("startedAt")
            if run_ids is None and type(started) is int and 0 < started <= 253402300799999 and started >= until.timestamp() * 1000:
                continue
            with (folder / "session.jsonl").open("rb") as stream:
                stat = os.fstat(stream.fileno())
                # Both metadata and journal mtime must predate the window.
                # A later append is deferred to the next collection, just like
                # bytes appended after the size snapshot below.
                updated = meta.get("updatedAt")
                if (run_ids is None
                        and type(updated) is int and 0 < updated <= 253402300799999
                        and updated < since.timestamp() * 1000
                        and stat.st_mtime < since.timestamp()):
                    continue
                size = stat.st_size
                data = stream.read(size)
            events = []
            for line in data.splitlines():
                try:
                    event = json.loads(line)
                    if isinstance(event, dict) and type(event.get("ts")) is int and 0 <= event["ts"] <= 253402300799999:
                        events.append(event)
                except (ValueError, UnicodeError, RecursionError):
                    continue
        except (OSError, ValueError, UnicodeError, RecursionError):
            continue
        events.sort(key=lambda e: e["ts"])
        models: dict[str, str] = {}
        providers: dict[str, str] = {}
        turns: dict[str, dict[str, Any]] = {}
        calls: dict[tuple[str, str], dict[str, Any]] = {}
        active: dict[str, str] = {}
        cwd = meta.get("cwd")
        root = None
        if isinstance(cwd, str) and os.path.isabs(cwd):
            try:
                directory = Path(cwd).resolve()
                root = next((p for p in (directory, *directory.parents) if (p / ".git").exists()), None)
            except (OSError, ValueError, RuntimeError):
                pass
        title = meta.get("title")
        task = TASK_KEY_RE.search(title) if isinstance(title, str) else None

        def finish(trace: dict[str, Any], status: str, ts: int) -> None:
            if trace["status"] != "running":
                return
            trace["status"] = trace["final_state"] = status
            trace["completed_at"] = _timestamp(ts)
            trace["duration_ms"] = ts - trace["_start"]

        for event in events:
            kind, ts = event.get("k"), event["ts"]
            tab = event.get("tabId")
            if kind == "tab" and isinstance(tab, str) and isinstance(event.get("patch"), dict):
                model = event["patch"].get("activeModel")
                if isinstance(model, str):
                    prefix = model.split("/", 1)[0]
                    if prefix in {"proxy", "subscriptions", "openai", "anthropic", "google", "minimax"}:
                        providers[tab] = prefix
                    else:
                        providers.pop(tab, None)
                    if safe_model_id(model):
                        models[tab] = model
                    else:
                        models.pop(tab, None)
            turn = event.get("turnId")
            turn_hash = _id(turn)
            if not turn_hash:
                continue
            run_id = "empryo-" + turn_hash
            if kind == "user":
                if run_id in turns:
                    continue
                if isinstance(tab, str) and tab in active:
                    previous = turns[active[tab]]
                    if previous["status"] == "running":
                        finish(previous, "interrupted", ts)
                started = _timestamp(ts)
                model = models.get(tab) if isinstance(tab, str) else None
                turns[run_id] = {"schema": "mac-ops.session_trace.v1", "source": "empryo", "run_id": run_id, "thread_id": "empryo-" + thread_hash, "provider": providers.get(tab) if isinstance(tab, str) else None, "model": model, "status": "running", "final_state": "running", "task_key": task.group(1) if task else None, "project_id": _id(str(root)) if root else None, "project": None, "title": None, "worktree_path": None, "branch": None, "tokens": None, "cost_usd": None, "pull_requests": [], "named_blocker": None, "files_outside_worktree": None, "preview_or_playwright": [], "requested_at": started, "started_at": started, "tool_calls": [], "outcome_evidence": "unknown", "_start": ts}
                if isinstance(tab, str):
                    active[tab] = run_id
                continue
            trace = turns.get(run_id)
            if trace is None:
                continue
            if kind == "assistant":
                raw_status = event.get("status")
                status = {"complete": "completed", "error": "failed"}.get(raw_status) if isinstance(raw_status, str) else None
                if status:
                    finish(trace, status, ts)
            elif kind == "turn-stop":
                finish(trace, "interrupted", ts)
            elif kind == "tool-start":
                call_id = event.get("toolCallId")
                name = event.get("name")
                if isinstance(call_id, str):
                    safe_name = name if isinstance(name, str) and name in TOOLS else "other"
                    call = {"name": safe_name, "type": "tool", "_start": ts}
                    trace["tool_calls"].append(call)
                    calls[(run_id, call_id)] = call
                    args = event.get("args")
                    nested_name = args.get("name") if name == "run_tool" and isinstance(args, dict) else None
                    if any(isinstance(n, str) and (PREVIEW_RE.search(n) or n == "computer_preview") for n in (name, nested_name)):
                        trace["preview_or_playwright"].append("preview")
                    # Session cwd identifies a project, not the worktree assigned
                    # to this turn. Without reliable assignment metadata, the
                    # outside-worktree result must remain unknown.
            elif kind == "tool-end":
                call_id = event.get("toolCallId")
                call = calls.pop((run_id, call_id), None) if isinstance(call_id, str) else None
                if call is not None:
                    call["duration_ms"] = ts - call["_start"]
        for run_id, trace in turns.items():
            start = trace.pop("_start")
            # Age is not terminal evidence; unknown turns remain reconcilable.
            if trace["status"] == "running" and start < (datetime.now(timezone.utc) - timedelta(days=3)).timestamp() * 1000:
                trace["status"] = trace["final_state"] = "unknown"
            for call in trace["tool_calls"]:
                call.pop("_start", None)
            trace["tool_call_count"] = len(trace["tool_calls"])
            if (run_ids is not None and run_id in run_ids) or (run_ids is None and since.timestamp() * 1000 <= start < until.timestamp() * 1000):
                traces[run_id] = trace
                if remaining is not None:
                    remaining.discard(run_id)
    return sorted(traces.values(), key=lambda t: (t["started_at"], t["run_id"]))
