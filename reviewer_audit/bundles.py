"""Freeze and load review benchmark bundles."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .board_io import git_diff_at_head, read_closing_note, read_task, task_repo_root
from .requirements import requirement_ids_for_finding

MANIFEST_VERSION = 2


@dataclass
class AdjudicatedDefect:
    requirement_id: str
    severity: str
    note: str = ""


@dataclass
class ReviewBundle:
    bundle_id: str
    task_id: str
    review_round: int
    head: str
    cohort: str  # regression-bad | regression-clean | history
    expected_pass: bool | None
    adjudicated_defects: list[AdjudicatedDefect] = field(default_factory=list)
    title: str = ""
    description: str = ""
    stat: str = ""
    diff_text: str = ""
    saved_proof: str = ""
    agent_closing_note: str = ""
    saved_review_pass: bool | None = None
    saved_finding_subjects: list[str] = field(default_factory=list)
    saved_requirement_ids: list[str] = field(default_factory=list)
    input_hash: str = ""
    # Legacy fields kept for manifest readers
    description_excerpt: str = ""
    closing_note_excerpt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cap(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _closing_note_for_head(closing: str, head: str) -> str:
    """Include agent closing note only when it plausibly describes this commit."""
    if not closing.strip() or not head:
        return ""
    head_prefix = head.lower()[:12]
    if head_prefix not in closing.lower():
        return ""
    # Reject notes centered on a different final commit hash.
    for match in re.finditer(r"\b([0-9a-f]{7,40})\b", closing.lower()):
        token = match.group(1)
        if (
            len(token) >= 12
            and not head.lower().startswith(token)
            and not token.startswith(head.lower()[: min(len(token), 12)])
        ) and ("final commit" in closing.lower() or "merged" in closing.lower()):
            return ""
    return closing.strip()


def saved_proof_from_review(review: dict[str, Any]) -> str:
    chunks: list[str] = []
    text = str(review.get("text") or "").strip()
    if text:
        chunks.append(f"review_summary:\n{text}")
    for f in review.get("findings") or []:
        fid = f.get("id", "?")
        subj = f.get("subject", "")
        where = f.get("where", "")
        proof = f.get("proof", "")
        chunks.append(
            f"finding {fid} ({f.get('severity', '')}): {subj}\n"
            f"where: {where}\nproof: {proof}"
        )
    checks = review.get("checks") or []
    if checks:
        chunks.append("checks:\n" + "\n".join(f"- {c}" for c in checks))
    limitations = review.get("limitations") or []
    if limitations:
        chunks.append("limitations:\n" + "\n".join(f"- {l}" for l in limitations))
    return "\n\n".join(chunks)


def _bundle_input_material(
    task: dict[str, Any],
    review: dict[str, Any],
    *,
    description: str,
    diff_text: str,
    saved_proof: str,
    agent_closing_note: str,
) -> str:
    parts = [
        task.get("id", ""),
        str(review.get("round", "")),
        str(review.get("head") or task.get("reviewedHead") or ""),
        task.get("title", ""),
        description,
        task.get("stat") or "",
        diff_text,
        saved_proof,
        agent_closing_note,
        json.dumps(review.get("checks") or [], sort_keys=True),
        json.dumps(review.get("limitations") or [], sort_keys=True),
    ]
    return "\n---\n".join(parts)


def input_hash_for_material(material: str) -> str:
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def bundle_from_task_round(
    task_id: str,
    review_round: int,
    *,
    cohort: str,
    expected_pass: bool | None,
    adjudicated: list[AdjudicatedDefect] | None = None,
    tasks_root: Path | None = None,
) -> ReviewBundle:
    task = read_task(task_id, tasks_root)
    reviews = task.get("reviews") or []
    review = next((r for r in reviews if r.get("round") == review_round), None)
    if review is None:
        raise ValueError(f"{task_id} has no review round {review_round}")
    head = str(review.get("head") or "")
    description = str(task.get("description") or "")
    repo_root = task_repo_root(task)
    git_stat, diff_text = git_diff_at_head(repo_root, head) if repo_root else ("", "")
    stat = git_stat or str(task.get("stat") or "")
    saved_proof = saved_proof_from_review(review)
    closing_raw = read_closing_note(task_id, tasks_root)
    agent_note = _closing_note_for_head(closing_raw, head)
    material = _bundle_input_material(
        task,
        review,
        description=description,
        diff_text=diff_text,
        saved_proof=saved_proof,
        agent_closing_note=agent_note,
    )
    ih = input_hash_for_material(material)
    bundle_id = f"{task_id.replace('/', '-')}--r{review_round}--{ih}"
    subjects: list[str] = []
    req_ids: list[str] = []
    for f in review.get("findings") or []:
        subj = str(f.get("subject") or "")
        if subj:
            subjects.append(subj)
        for rid in requirement_ids_for_finding(f):
            if rid not in req_ids:
                req_ids.append(rid)
    return ReviewBundle(
        bundle_id=bundle_id,
        task_id=task_id,
        review_round=review_round,
        head=head,
        cohort=cohort,
        expected_pass=expected_pass,
        adjudicated_defects=adjudicated or [],
        title=str(task.get("title") or ""),
        description=description,
        stat=stat,
        diff_text=diff_text,
        saved_proof=saved_proof,
        agent_closing_note=agent_note,
        saved_review_pass=bool(review.get("pass"))
        if review.get("pass") is not None
        else None,
        saved_finding_subjects=subjects,
        saved_requirement_ids=req_ids,
        input_hash=ih,
        description_excerpt=_cap(description, 2000),
        closing_note_excerpt=_cap(agent_note, 3000),
    )


def default_seed_bundles(tasks_root: Path | None = None) -> list[ReviewBundle]:
    """Curated regression set from LMW-25 evidence and task brief."""
    seeds: list[tuple[str, int, str, bool | None, list[AdjudicatedDefect]]] = [
        (
            "llmwiki/10",
            7,
            "regression-bad",
            False,
            [
                AdjudicatedDefect("REQ-NATIVE-START-GATE", "critical"),
                AdjudicatedDefect("REQ-LIVE-ACCEPTANCE", "major"),
            ],
        ),
        (
            "llmwiki/10",
            9,
            "regression-bad",
            False,
            [AdjudicatedDefect("REQ-LIVE-ACCEPTANCE", "major")],
        ),
        (
            "strategy-replay-workbench/61",
            1,
            "regression-bad",
            False,
            [
                AdjudicatedDefect("REQ-SPX-LEVEL-TRACK", "critical"),
                AdjudicatedDefect("REQ-EXIT-SIZING", "major"),
                AdjudicatedDefect("REQ-API-EVIDENCE", "major"),
            ],
        ),
        (
            "strategy-replay-workbench/61",
            13,
            "regression-bad",
            False,
            [AdjudicatedDefect("REQ-SPX-LEVEL-TRACK", "critical")],
        ),
        (
            "strategy-replay-workbench/86",
            1,
            "regression-clean",
            True,
            [],
        ),
        (
            "strategy-replay-workbench/73",
            3,
            "regression-clean",
            True,
            [],
        ),
        (
            "strategy-replay-workbench/77",
            3,
            "regression-clean",
            True,
            [],
        ),
        (
            "llmwiki/25",
            4,
            "regression-clean",
            True,
            [],
        ),
    ]
    bundles: list[ReviewBundle] = []
    for task_id, rnd, cohort, exp_pass, adj in seeds:
        try:
            bundles.append(
                bundle_from_task_round(
                    task_id,
                    rnd,
                    cohort=cohort,
                    expected_pass=exp_pass,
                    adjudicated=adj,
                    tasks_root=tasks_root,
                )
            )
        except (ValueError, OSError, json.JSONDecodeError):
            continue

    extras: list[tuple[str, int, str, bool | None]] = [
        ("strategy-replay-workbench/81", 1, "history", False),
        ("strategy-replay-workbench/81", 2, "history", False),
        ("strategy-replay-workbench/72", 1, "history", False),
        ("strategy-replay-workbench/72", 2, "history", False),
        ("llmwiki/12", 1, "history", False),
        ("llmwiki/12", 9, "history", True),
        ("CineJar/4", 1, "history", False),
        ("CineJar/4", 2, "history", True),
        ("scripture-scroll/1", 1, "history", False),
        ("scripture-scroll/1", 2, "history", True),
        ("recoup/3", 1, "history", False),
        ("dbt/3", 1, "history", False),
        ("omni/8", 1, "history", False),
        ("mac-ops/8", 1, "history", False),
        ("mac-ops/7", 1, "history", False),
        ("strategy-replay-workbench/80", 1, "history", False),
        ("strategy-replay-workbench/83", 1, "history", True),
        ("llmwiki/24", 1, "history", False),
    ]
    seen = {b.bundle_id for b in bundles}
    for task_id, rnd, cohort, exp_pass in extras:
        try:
            b = bundle_from_task_round(
                task_id,
                rnd,
                cohort=cohort,
                expected_pass=exp_pass,
                tasks_root=tasks_root,
            )
        except (ValueError, OSError, json.JSONDecodeError):
            continue
        if b.bundle_id in seen:
            continue
        seen.add(b.bundle_id)
        bundles.append(b)
        if len(bundles) >= 24:
            break
    return bundles


def write_manifest(path: Path, bundles: list[ReviewBundle]) -> None:
    doc = {
        "version": MANIFEST_VERSION,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "bundle_count": len(bundles),
        "bundles": [b.to_dict() for b in bundles],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def load_manifest(path: Path) -> tuple[dict[str, Any], list[ReviewBundle]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    bundles = []
    for raw in doc.get("bundles") or []:
        adj = [
            AdjudicatedDefect(**a) if isinstance(a, dict) else a
            for a in raw.get("adjudicated_defects") or []
        ]
        raw = dict(raw)
        raw["adjudicated_defects"] = adj
        raw.setdefault("description", raw.get("description_excerpt", ""))
        raw.setdefault("diff_text", "")
        raw.setdefault("saved_proof", "")
        raw.setdefault("agent_closing_note", raw.get("closing_note_excerpt", ""))
        bundles.append(ReviewBundle(**raw))
    return doc, bundles
