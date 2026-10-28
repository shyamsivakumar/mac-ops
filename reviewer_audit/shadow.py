"""Shadow review replay on frozen bundles."""

from __future__ import annotations

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .board_io import read_reviewer_instructions
from .bundles import ReviewBundle, _cap
from .judge import run_model_prompt
from .metrics import ShadowVerdict
from .requirements import requirement_ids_for_subject

LEGACY_PASS_RULE = (
    "pass=false if critical or major acceptance gaps remain in the proof."
)
SHIP_AND_SCORE_PASS_RULE = (
    "Set pass=false only for hard stops or when the change does not do what the "
    "task asked at all, matching reviewer.instructions below. List other gaps in "
    "findings with severity; they are follow-ups and must not force pass=false "
    "unless they are blocking findings with a named task requirement and a failing "
    "reproduction."
)

PROMPT_DIFF_CAP = 48_000
PROMPT_PROOF_CAP = 32_000
PROMPT_DESC_CAP = 12_000
PROMPT_NOTE_CAP = 8_000


def _shadow_prompt(
    bundle: ReviewBundle,
    *,
    review_policy: str = "board",
    reviewer_instructions: str | None = None,
) -> str:
    desc = _cap(bundle.description or bundle.description_excerpt, PROMPT_DESC_CAP)
    diff = _cap(bundle.diff_text, PROMPT_DIFF_CAP)
    proof = _cap(bundle.saved_proof, PROMPT_PROOF_CAP)
    note = _cap(
        bundle.agent_closing_note or bundle.closing_note_excerpt, PROMPT_NOTE_CAP
    )
    if not diff.strip():
        diff = "(diff unavailable at freeze — verify repo checkout and head)"
    if not proof.strip():
        proof = "(saved review proof missing at freeze)"
    if review_policy == "legacy":
        pass_rule = LEGACY_PASS_RULE
        policy_block = ""
    else:
        pass_rule = SHIP_AND_SCORE_PASS_RULE
        instr = reviewer_instructions or read_reviewer_instructions()
        policy_block = f"reviewer.instructions (board mac-ops):\n{instr}\n\n"
    return (
        "Board shadow review on a frozen historical bundle. "
        "Use only the materials below.\n"
        "Reply with JSON only, no markdown:\n"
        '{"pass":bool,"findings":[{"severity":"critical|major|minor","subject":"..."}]}\n'
        f"{pass_rule}\n\n"
        f"{policy_block}"
        f"task={bundle.task_id}\nreview_round={bundle.review_round}\n"
        f"commit={bundle.head}\nbase={bundle.diff_base}\ninput_hash={bundle.input_hash}\n"
        f"title={bundle.title[:200]}\nstat={bundle.stat}\n\n"
        f"task_description:\n{desc}\n\n"
        f"source_diff:\n{diff}\n\n"
        f"saved_review_proof:\n{proof}\n\n"
        f"agent_closing_note_at_commit:\n{note or '(none for this commit)'}\n"
    )


def _extract_json_verdict(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if not text:
        return None
    candidates: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            candidates.append(line)
    candidates.append(text)
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    match = re.search(r"\{[\s\S]*?\}\s*(?:\n|$)", text)
    if match:
        try:
            obj = json.loads(match.group(0).strip())
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    return None


def _parse_verdict(raw: str, model: str, repeat: int) -> ShadowVerdict:
    parsed = _extract_json_verdict(raw)
    if not parsed:
        return ShadowVerdict(
            pass_verdict=False,
            finding_subjects=[],
            requirement_ids=[],
            model=model,
            repeat=repeat,
            raw=raw[:800],
            error=True,
        )
    if parsed.get("error"):
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
    review_policy: str = "board",
    reviewer_instructions: str | None = None,
) -> list[ShadowVerdict]:
    if use_models and use_heavy:
        return replay_bundle_heavy(
            bundle,
            repeats=repeats,
            bundle_index=bundle_index,
            review_policy=review_policy,
            reviewer_instructions=reviewer_instructions,
        )
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

    prompt = _shadow_prompt(
        bundle,
        review_policy=review_policy,
        reviewer_instructions=reviewer_instructions,
    )

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
    bundle: ReviewBundle,
    *,
    repeats: int = 5,
    bundle_index: int = 0,
    review_policy: str = "board",
    reviewer_instructions: str | None = None,
) -> list[ShadowVerdict]:
    """Run each repeat through ~/.local/bin/heavy --review."""
    prompt = _shadow_prompt(
        bundle,
        review_policy=review_policy,
        reviewer_instructions=reviewer_instructions,
    )
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
