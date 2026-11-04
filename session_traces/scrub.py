"""Scrub secrets, key-bearing prompts, and personal data from traces."""

from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime
from typing import Any

# Field names whose values are dropped entirely (case-insensitive).
DROP_FIELDS = frozenset(
    {
        "authorization",
        "cookie",
        "cookies",
        "password",
        "passwd",
        "secret",
        "secrets",
        "token",
        "api_key",
        "apikey",
        "access_key",
        "private_key",
        "client_secret",
        "refresh_token",
        "id_token",
        "session_token",
        "prompt",
        "system_prompt",
        "user_prompt",
        "messages",
        "message",
        "message_body",
        "title",
        "content",
        "text",
        "body",
        "input",
        "output",
        "arguments",
        "diffstr",
        "diff",
        "aggregatedoutput",
        "email",
        "phone",
        "ssn",
        "address",
    }
)

# Patterns replaced with [REDACTED] inside remaining strings.
SECRET_PATTERNS = [
    re.compile(r"(?<![A-Za-z0-9_])hf_[A-Za-z0-9]{20,}(?![A-Za-z0-9_])"),
    re.compile(r"(?<![A-Za-z0-9_])(?:sk|pk|key|token|secret|api)[_-][A-Za-z0-9_-]{16,}(?![A-Za-z0-9_])", re.IGNORECASE),

    re.compile(r"(?<![A-Za-z0-9_])(?:ghu|ghs|ghr)_[A-Za-z0-9]{20,}(?![A-Za-z0-9_])"),
    re.compile(r"(?<![A-Za-z0-9_])(?:pypi-|npm_|xox[baprs]-)[A-Za-z0-9_-]{10,}(?![A-Za-z0-9_])"),
    re.compile(r"\b(phc_[A-Za-z0-9]+)\b"),
    re.compile(r"\b(phx_[A-Za-z0-9]+)\b"),
    re.compile(r"\b(sk-[A-Za-z0-9_-]{10,})\b"),
    re.compile(r"\b(sk-ant-[A-Za-z0-9_-]{10,})\b"),
    re.compile(r"\b(ghp_[A-Za-z0-9]{20,})\b"),
    re.compile(r"\b(gho_[A-Za-z0-9]{20,})\b"),
    re.compile(r"\b(github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\b(glpat-[A-Za-z0-9_-]{20,})\b"),
    re.compile(r"\b(xox[baprs]-[A-Za-z0-9-]{10,})\b"),
    re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
    re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._\-+=/]{8,}"),
    re.compile(r"(?i)\b(Authorization:\s*Basic\s+)[A-Za-z0-9+/=]+"),
    # No minimum length: short values like YTpi ("a:b") must redact too.
    re.compile(r"(?i)(?<![\w-])(Basic\s+)[A-Za-z0-9+/=]+"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*\S+"),
    # curl -u user:pass and basic-auth style credentials in command text
    re.compile(r"(?i)(-u|--user)\s+\S+:\S+"),
    re.compile(r"(?i)://[^/\s:]+:[^/\s@]+@"),
    # Phone / SSN (US-oriented; still scrub when present in titles)
    re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"/Users/[^/\s]+"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
]

HOME_RE = re.compile(r"^/Users/[^/]+")


def scrub_string(value: str) -> str:
    out = value
    for pat in SECRET_PATTERNS:
        if (
            "Bearer" in pat.pattern
            or "Basic" in pat.pattern
            or (pat.pattern.startswith("(?i)(api") and "password" in pat.pattern)
        ):
            out = pat.sub(
                lambda m: (m.group(1) if m.lastindex else "") + "[REDACTED]", out
            )
        elif pat.pattern.startswith("(?i)(-u"):
            out = pat.sub(r"\1 [REDACTED]", out)
        elif pat is HOME_RE or pat.pattern.startswith("/Users"):
            out = pat.sub("/Users/[user]", out)
        else:
            out = pat.sub("[REDACTED]", out)
    return out


def scrub_path(path: str | None) -> str | None:
    if not path:
        return path
    return HOME_RE.sub("/Users/[user]", path)


def _drop_field(field: str) -> bool:
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", field).lower().replace("-", "_")
    return (normalized in DROP_FIELDS or normalized.endswith("_title")
            or normalized.endswith("_message") or normalized.endswith("_message_body"))


def scrub_value(value: Any, *, field: str | None = None) -> Any:
    if field and field.lower().replace("-", "_") in {"model", "model_id", "modelid", "activemodel", "active_model"}:
        return safe_model_id(value)
    if field and _drop_field(field):
        return "[DROPPED]"
    if isinstance(value, dict):
        return {
            k: scrub_value(v, field=str(k))
            for k, v in value.items()
            if not _drop_field(str(k)) and (not isinstance(k, str) or scrub_string(k) == k)
        }
    if isinstance(value, (list, tuple)):
        return [scrub_value(v, field=field) for v in value]
    if isinstance(value, str):
        return scrub_string(value)
    return value


def scrub_trace(trace: dict[str, Any]) -> dict[str, Any]:
    """Return a copy safe to persist or ship (no prompts, secrets, PII)."""
    return scrub_value(trace)  # type: ignore[return-value]


# Exact identifiers only: syntax and token-pattern checks cannot establish trust.
KNOWN_MODEL_IDS = frozenset({
    "proxy/gpt-6.1-terra", "proxy/gpt-6.1-sol", "proxy/gpt-6-luna",
    "subscriptions/gpt-6.1-terra", "subscriptions/gpt-6.1-sol",
    "subscriptions/gpt-6-luna", "subscriptions/claude-opus-5-5",
    "subscriptions/claude-sonnet-5-5", "minimax/MiniMax-M3.1-Flash",
    "anthropic/claude-opus-4-6", "anthropic/claude-sonnet-4-6",
    "anthropic/claude-sonnet-4-5", "anthropic/claude-opus-4-5",
    "openai/gpt-5.4", "openai/gpt-5.3-codex", "openai/gpt-5.2-codex",
    "openai/gpt-5.2", "openai/gpt-5.1-codex", "openai/gpt-5-codex",
    "google/gemini-3-pro-preview", "google/gemini-3.1-pro-preview",
    "claude-opus-4-6", "claude-sonnet-4-6", "claude-sonnet-4-5",
    "gpt-5.4", "gpt-5.3-codex", "gpt-5.2-codex", "gpt-5.2",
})


def safe_model_id(value: Any) -> str | None:
    return value if isinstance(value, str) and value in KNOWN_MODEL_IDS else None


def _hash_identifier(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return hashlib.sha256(value.encode("utf-8", errors="surrogatepass")).hexdigest()


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _enum(value: Any, choices: frozenset[str]) -> str | None:
    return value if isinstance(value, str) and value in choices else None


def _timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None
        return dt.isoformat()
    except ValueError:
        return None


_STATUS = frozenset("running queued pending completed complete failed error interrupted cancelled canceled unknown success failure timed_out skipped".split())
_TOOL_NAMES = frozenset("shell code_script read run_tool final_response ast_edit grep project edit_file git shell_jobs navigate genome_impact tool_search multi_edit find show refactor link command_execution file_change file_search web_search subagent dynamic_tool other".split())
_TOKEN_KEYS = frozenset("inputTokens outputTokens totalTokens cachedInputTokens reasoningTokens turnsComplete turnsPartial turnsUnavailable input_tokens output_tokens total_tokens cached_input_tokens costUsd totalCostUsd cost_usd".split())


def safe_export_projection(trace: dict[str, Any]) -> dict[str, Any]:
    """Project untrusted trace data to explicitly typed, non-content telemetry."""
    out: dict[str, Any] = {}
    for key in ("run_id", "thread_id", "project_id", "task_key", "branch"):
        if key in trace:
            out[key] = _hash_identifier(trace[key])
    for key in ("ordinal", "duration_ms", "cost_usd"):
        if key in trace:
            out[key] = _number(trace[key])
    for key in ("requested_at", "started_at", "completed_at"):
        if key in trace:
            out[key] = _timestamp(trace[key])
    for key in ("status", "final_state"):
        if key in trace:
            out[key] = _enum(trace[key], _STATUS)
    for key, choices in {
        "schema": frozenset({"mac-ops.session_trace.v1"}),
        "source": frozenset({"empryo", "t3"}),
        "provider": frozenset({"anthropic", "openai", "google", "proxy", "subscriptions", "minimax", "codex", "claude", "cursor", "other"}),
        "outcome_evidence": frozenset({"known", "unknown"}),
    }.items():
        if key in trace:
            out[key] = _enum(trace[key], choices)
    if "model" in trace:
        out["model"] = safe_model_id(trace["model"])
    tokens = trace.get("tokens")
    if isinstance(tokens, dict):
        out["tokens"] = {k: _number(tokens[k]) for k in _TOKEN_KEYS if k in tokens and _number(tokens[k]) is not None}
    calls = trace.get("tool_calls")
    if isinstance(calls, list):
        out["tool_call_count"] = len(calls)
        out["tool_calls_summary"] = [
            {"name": _enum(c.get("name"), _TOOL_NAMES) or "other",
             "type": _enum(c.get("type"), _TOOL_NAMES | frozenset({"tool"})),
             "duration_ms": _number(c.get("duration_ms")),
             "status": _enum(c.get("status"), _STATUS)}
            for c in calls[:200] if isinstance(c, dict)
        ]
    prs = trace.get("pull_requests")
    if isinstance(prs, list):
        result = []
        for pr in prs[:200]:
            if not isinstance(pr, dict):
                continue
            item: dict[str, Any] = {}
            for key in ("repository", "url", "head_branch"):
                if key in pr:
                    item[key] = _hash_identifier(pr[key])
            number = pr.get("number")
            if type(number) is int and number > 0:
                item["number"] = number
            sha = pr.get("merge_sha")
            if isinstance(sha, str) and re.fullmatch(r"[a-fA-F0-9]{40}|[a-fA-F0-9]{64}", sha):
                item["merge_sha"] = sha
            for key, choices in {
                "state": frozenset({"open", "closed", "merged", "merged_unknown_timing"}),
                "timing": frozenset({"known", "unknown", "post_run_merge"}),
                "checks_state": frozenset({"SUCCESS", "FAILURE", "PENDING", "ERROR", "EXPECTED", "success", "failure", "pending", "error", "passing", "failing", "failed", "unknown"}),
                "review_decision": frozenset({"APPROVED", "CHANGES_REQUESTED", "REVIEW_REQUIRED"}),
            }.items():
                if key in pr:
                    item[key] = _enum(pr[key], choices)
            for key in ("evidence_by_end", "merge_by_end"):
                if type(pr.get(key)) is bool:
                    item[key] = pr[key]
            if "merged_at" in pr:
                item["merged_at"] = _timestamp(pr["merged_at"])
            result.append(item)
        out["pull_requests"] = result
    return out
