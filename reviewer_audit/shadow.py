"""Shadow review replay on frozen bundles."""

from __future__ import annotations

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .bundles import ReviewBundle
from .judge import run_model_prompt
from .metrics import ShadowVerdict
from .requirements import requirement_ids_for_subject


def _shadow_prompt(bundle: ReviewBundle) -> str:
    note = bundle.closing_note_excerpt[:1200]
    desc = bundle.description_excerpt[:800]
    return (
        "Board shadow review. Reply with JSON only, no markdown:\n"
        '{"pass":bool,"findings":[{"severity":"critical|major|minor","subject":"..."}]}\n'
        "pass=false if critical or major acceptance gaps remain in the proof.\n"
        f"task={bundle.task_id}\ncommit={bundle.head}\n"
        f"title={bundle.title[:120]}\nstat={bundle.stat}\n"
        f"brief={desc}\nproof={note}\n"
    )


def _parse_verdict(raw: str, model: str, repeat: int) -> ShadowVerdict:
    parsed: dict[str, Any] | None = None
    try:
        parsed = json.loads(raw.strip())
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                parsed = None
    if not parsed or parsed.get("error"):
        return ShadowVerdict(
            pass_verdict=False,
            finding_subjects=[],
            requirement_ids=[],
            model=model,
            repeat=repeat,
            raw=raw[:800],
            error=True,
        )
    if parsed.get("pass") is None:
        return ShadowVerdict(
            pass_verdict=False,
            finding_subjects=[],
            requirement_ids=[],
            model=model,
            repeat=repeat,
            raw=raw[:800],
            error=True,
        )
    findings = parsed.get("findings") or []
    subjects = [str(f.get("subject") or "") for f in findings if f.get("subject")]
    req_ids: list[str] = []
    for s in subjects:
        for rid in requirement_ids_for_subject(s):
            if rid not in req_ids:
                req_ids.append(rid)
    return ShadowVerdict(
        pass_verdict=bool(parsed.get("pass")),
        finding_subjects=subjects,
        requirement_ids=req_ids,
        model=model,
        repeat=repeat,
        raw=raw[:800],
        error=False,
    )


def model_for_bundle_index(bundle_index: int) -> str:
    return ("gpt-6.1", "claude-opus", "gpt-6.1")[bundle_index % 3]


def replay_bundle(
    bundle: ReviewBundle,
    *,
    repeats: int = 5,
    use_models: bool = True,
    use_heavy: bool = False,
    timeout: int = 180,
    bundle_index: int = 0,
) -> list[ShadowVerdict]:
    if use_models and use_heavy:
        return replay_bundle_heavy(bundle, repeats=repeats, bundle_index=bundle_index)
    model = model_for_bundle_index(bundle_index)
    if not use_models:
        raw = json.dumps(
            {
                "pass": bundle.saved_review_pass,
                "findings": [
                    {"severity": "major", "subject": s}
                    for s in bundle.saved_finding_subjects[:3]
                ],
            }
        )
        return [_parse_verdict(raw, "saved", i + 1) for i in range(repeats)]

    prompt = _shadow_prompt(bundle)

    def one(repeat: int) -> ShadowVerdict:
        try:
            raw = run_model_prompt(model, prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            return ShadowVerdict(
                pass_verdict=False,
                finding_subjects=[],
                requirement_ids=[],
                model=model,
                repeat=repeat,
                raw="timeout",
                error=True,
            )
        return _parse_verdict(raw, model, repeat)

    out: list[ShadowVerdict] = []
    with ThreadPoolExecutor(max_workers=repeats) as pool:
        futures = [pool.submit(one, i + 1) for i in range(repeats)]
        for fut in as_completed(futures):
            out.append(fut.result())
    out.sort(key=lambda v: v.repeat)
    return out


def replay_bundle_heavy(
    bundle: ReviewBundle, *, repeats: int = 5, bundle_index: int = 0
) -> list[ShadowVerdict]:
    """Run each repeat through ~/.local/bin/heavy --review."""
    prompt = _shadow_prompt(bundle)
    model = model_for_bundle_index(bundle_index)
    out: list[ShadowVerdict] = []
    for i in range(repeats):
        if model == "gpt-6.1":
            inner = ["codex", "exec", "-m", "gpt-6.1-sol", prompt]
        else:
            inner = ["claude", "-p", "--model", "opus", prompt]
        argv = ["/Users/shyamsivakumar/.local/bin/heavy", "--review", *inner]
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            raw = (proc.stdout or "") + (proc.stderr or "")
        except subprocess.TimeoutExpired:
            raw = "timeout"
        out.append(_parse_verdict(raw, model, i + 1))
    return out
