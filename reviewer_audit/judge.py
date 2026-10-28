"""Mixed-model shadow judge (bounded Noul-style questions)."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any

MODEL_ROTATION: tuple[tuple[str, str], ...] = (
    ("gpt-6.1", "codex"),
    ("claude-opus", "claude"),
    ("minimax", "pi"),
)


@dataclass
class JudgeQuestion:
    question_id: str
    text: str
    kind: str  # noul | score | choice


BOUNDED_QUESTIONS: tuple[JudgeQuestion, ...] = (
    JudgeQuestion(
        "boundary-exercised",
        "The saved proof exercises the task's named acceptance boundary (not only local helpers).",
        "noul",
    ),
    JudgeQuestion(
        "receipt-supported",
        "The closing note cites an execution or replay receipt that supports the claimed result.",
        "noul",
    ),
    JudgeQuestion(
        "layer-match",
        "What evidence layer does the bundle establish?",
        "choice",
    ),
)


def _parse_json_blob(text: str) -> dict[str, Any] | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def run_model_prompt(model_key: str, prompt: str, timeout: int = 180) -> str:
    if model_key == "gpt-6.1":
        argv = ["codex", "exec", "-m", "gpt-6.1-sol", prompt]
    elif model_key == "claude-opus":
        argv = ["claude", "-p", "--model", "opus", prompt]
    elif model_key == "minimax":
        argv = ["pi", "--model", "minimax/MiniMax-M3.1-Flash", "-p", prompt]
    else:
        raise ValueError(f"unknown model key {model_key}")
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 and model_key == "minimax":
        return json.dumps(
            {
                "pass": None,
                "findings": [],
                "error": "minimax-unavailable",
                "detail": out[-400:],
            }
        )
    return out.strip()


def judge_bundle_layer(closing_excerpt: str, model_key: str) -> dict[str, Any]:
    prompt = (
        'Answer with JSON only: {"layer": one of '
        '"source","local_replay","ci","deployed","live","unknown", '
        '"confidence": 0.0-1.0}\n\n'
        f"Closing note and proof excerpt:\n{closing_excerpt[:3500]}"
    )
    raw = run_model_prompt(model_key, prompt)
    parsed = _parse_json_blob(raw) or {
        "layer": "unknown",
        "confidence": 0.0,
        "raw": raw[:500],
    }
    parsed["model"] = model_key
    return parsed
