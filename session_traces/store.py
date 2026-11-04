"""Local NDJSON store plus optional PostHog export."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .scrub import safe_export_projection, scrub_trace

DEFAULT_STATE = Path.home() / ".local" / "state" / "mac-ops"
DEFAULT_POSTHOG_HOST = "https://us.i.posthog.com"
LOCAL_TZ = ZoneInfo("America/Los_Angeles")


def state_root(root: Path | None = None) -> Path:
    return Path(root) if root else Path(os.environ.get("MAC_OPS_STATE", DEFAULT_STATE))


def traces_dir(root: Path | None = None, day: str | None = None) -> Path:
    base = state_root(root) / "session-traces"
    return base / day if day else base


def evals_dir(root: Path | None = None) -> Path:
    return state_root(root) / "session-evals"


def day_key(ts: str | datetime | None = None) -> str:
    if isinstance(ts, datetime):
        return ts.astimezone(LOCAL_TZ).strftime("%Y-%m-%d")
    if isinstance(ts, str) and ts:
        # ISO timestamps from T3 are UTC with Z.
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.astimezone(LOCAL_TZ).strftime("%Y-%m-%d")
        except ValueError:
            return ts[:10]
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")


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
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                traces.append(value)
        except (OSError, ValueError, RecursionError):
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
    """Export only terminal traces; preview uses the identical eligibility filter."""
    key = api_key if api_key is not None else posthog_api_key()
    if not key:
        return {"exported": 0, "skipped": "no_api_key"}
    host = (host or posthog_host()).rstrip("/")
    batch = []
    for trace in traces:
        status = trace.get("status")
        terminal = isinstance(status, str) and status.lower() in {
            "completed", "complete", "failed", "error", "timed_out", "skipped",
            "success", "failure", "interrupted", "cancelled", "canceled",
        }
        if not terminal:
            continue

        # Use the original identity so distinct IDs do not collapse after redaction.
        # Older traces use stable origin fields, never mutable status or usage.
        identity = [trace.get("source") or "", trace.get("run_id")]
        if not identity[1]:
            identity.extend(trace.get(k) for k in ("thread_id", "ordinal", "started_at", "requested_at"))
        event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(identity, sort_keys=True, separators=(",", ":"))))
        # Projection is an explicit typed allowlist, not general-purpose scrubbing.
        properties = safe_export_projection(trace)
        if terminal:
            properties["status"] = properties["final_state"] = status.lower()
        properties["$lib"] = "mac-ops-session-traces"
        batch.append(
            {
                "event": "agent_build_session",
                "uuid": event_id,
                "distinct_id": str(properties.get("thread_id") or properties.get("run_id") or "unknown"),
                "properties": properties,
                "timestamp": properties.get("started_at")
                or properties.get("requested_at")
                or "1970-01-01T00:00:00Z",
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
