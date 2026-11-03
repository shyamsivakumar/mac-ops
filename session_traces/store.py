"""Local NDJSON store plus optional PostHog export."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .scrub import scrub_trace

DEFAULT_STATE = Path.home() / ".local" / "state" / "mac-ops"
DEFAULT_POSTHOG_HOST = "https://us.i.posthog.com"


def state_root(root: Path | None = None) -> Path:
    return Path(root) if root else Path(os.environ.get("MAC_OPS_STATE", DEFAULT_STATE))


def traces_dir(root: Path | None = None, day: str | None = None) -> Path:
    base = state_root(root) / "session-traces"
    return base / day if day else base


def evals_dir(root: Path | None = None) -> Path:
    return state_root(root) / "session-evals"


def day_key(ts: str | datetime | None = None) -> str:
    if isinstance(ts, datetime):
        return ts.astimezone().strftime("%Y-%m-%d")
    if isinstance(ts, str) and ts:
        # ISO timestamps from T3 are UTC with Z.
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.astimezone().strftime("%Y-%m-%d")
        except ValueError:
            return ts[:10]
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def write_trace(trace: dict[str, Any], *, root: Path | None = None) -> Path:
    scrubbed = scrub_trace(trace)
    day = day_key(scrubbed.get("started_at") or scrubbed.get("requested_at"))
    out_dir = traces_dir(root, day)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(scrubbed.get("run_id") or "unknown").replace("/", "_")
    path = out_dir / f"{run_id}.json"
    path.write_text(
        json.dumps(scrubbed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def rebuild_day_index(day: str, *, root: Path | None = None) -> Path:
    out_dir = traces_dir(root, day)
    out_dir.mkdir(parents=True, exist_ok=True)
    index = out_dir / "index.ndjson"
    lines = []
    for path in sorted(out_dir.glob("*.json")):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        lines.append(json.dumps(obj, sort_keys=True))
    index.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return index


def load_day_traces(day: str, *, root: Path | None = None) -> list[dict[str, Any]]:
    out_dir = traces_dir(root, day)
    if not out_dir.is_dir():
        return []
    traces: list[dict[str, Any]] = []
    for path in sorted(out_dir.glob("*.json")):
        if path.name == "index.ndjson":
            continue
        try:
            traces.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return traces


def posthog_api_key() -> str | None:
    for name in (
        "POSTHOG_API_KEY",
        "POSTHOG_PROJECT_API_KEY",
        "MAC_OPS_POSTHOG_API_KEY",
    ):
        val = os.environ.get(name, "").strip()
        if val:
            return val
    key_file = os.environ.get("POSTHOG_API_KEY_FILE", "").strip()
    if key_file:
        try:
            return Path(key_file).read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
    return None


def posthog_host() -> str:
    return os.environ.get("POSTHOG_HOST", DEFAULT_POSTHOG_HOST).rstrip("/")


def export_posthog(
    traces: Iterable[dict[str, Any]],
    *,
    api_key: str | None = None,
    host: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Ship scrubbed run traces as PostHog capture events. No-op without a key."""
    key = api_key if api_key is not None else posthog_api_key()
    if not key:
        return {"exported": 0, "skipped": "no_api_key"}
    host = (host or posthog_host()).rstrip("/")
    batch = []
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for trace in traces:
        scrubbed = scrub_trace(trace)
        distinct = scrubbed.get("thread_id") or scrubbed.get("run_id") or "unknown"
        batch.append(
            {
                "event": "agent_build_session",
                "distinct_id": str(distinct),
                "properties": {
                    **{k: v for k, v in scrubbed.items() if k not in ("tool_calls",)},
                    "tool_call_count": len(scrubbed.get("tool_calls") or []),
                    "tool_calls_summary": [
                        {
                            "name": t.get("name"),
                            "type": t.get("type"),
                            "duration_ms": t.get("duration_ms"),
                            "status": t.get("status"),
                        }
                        for t in (scrubbed.get("tool_calls") or [])[:200]
                    ],
                    "$lib": "mac-ops-session-traces",
                },
                "timestamp": scrubbed.get("completed_at")
                or scrubbed.get("started_at")
                or now,
            }
        )
    if dry_run:
        return {"exported": len(batch), "dry_run": True, "host": host}
    if not batch:
        return {"exported": 0}
    body = json.dumps({"api_key": key, "batch": batch}).encode("utf-8")
    req = urllib.request.Request(
        f"{host}/batch/",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = getattr(resp, "status", 200)
            return {"exported": len(batch), "status": status, "host": host}
    except urllib.error.HTTPError as exc:
        return {"exported": 0, "error": f"http_{exc.code}", "host": host}
    except urllib.error.URLError as exc:
        return {"exported": 0, "error": f"url_{exc.reason}", "host": host}
