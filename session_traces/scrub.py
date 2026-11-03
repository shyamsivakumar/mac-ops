"""Scrub secrets, key-bearing prompts, and personal data from traces."""

from __future__ import annotations

import re
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
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*\S+"),
    re.compile(r"/Users/[^/\s]+"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
]

HOME_RE = re.compile(r"^/Users/[^/]+")


def scrub_string(value: str) -> str:
    out = value
    for pat in SECRET_PATTERNS:
        if pat.pattern.startswith("(?i)(api") or "Bearer" in pat.pattern:
            out = pat.sub(
                lambda m: (m.group(1) if m.lastindex else "") + "[REDACTED]", out
            )
        elif pat is HOME_RE or pat.pattern.startswith("/Users"):
            out = pat.sub("/Users/[user]", out)
        else:
            out = pat.sub("[REDACTED]", out)
    return out


def scrub_path(path: str | None) -> str | None:
    if not path:
        return path
    return HOME_RE.sub("/Users/[user]", path)


def scrub_value(value: Any, *, field: str | None = None) -> Any:
    if field and field.lower().replace("-", "_") in DROP_FIELDS:
        return "[DROPPED]"
    if isinstance(value, dict):
        return {
            k: scrub_value(v, field=str(k))
            for k, v in value.items()
            if str(k).lower().replace("-", "_") not in DROP_FIELDS
        }
    if isinstance(value, list):
        return [scrub_value(v, field=field) for v in value]
    if isinstance(value, str):
        return scrub_string(value)
    return value


def scrub_trace(trace: dict[str, Any]) -> dict[str, Any]:
    """Return a copy safe to persist or ship (no prompts, secrets, PII)."""
    return scrub_value(trace)  # type: ignore[return-value]
