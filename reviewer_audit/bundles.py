"""Freeze and load review benchmark bundles."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .board_io import read_closing_note, read_task
from .requirements import requirement_ids_for_finding

MANIFEST_VERSION = 1


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
    description_excerpt: str = ""
    stat: str = ""
    closing_note_excerpt: str = ""
    saved_review_pass: bool | None = None
    saved_finding_subjects: list[str] = field(default_factory=list)
    saved_requirement_ids: list[str] = field(default_factory=list)
    input_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _excerpt(text: str, limit: int = 2400) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _bundle_input_material(
    task: dict[str, Any],
    review: dict[str, Any],
    closing_note: str,
) -> str:
    parts = [
        task.get("id", ""),
        str(review.get("round", "")),
        str(review.get("head") or task.get("reviewedHead") or ""),
        task.get("title", ""),
        _excerpt(str(task.get("description") or ""), 4000),
        task.get("stat") or "",
        _excerpt(closing_note, 6000),
        json.dumps(review.get("checks") or [], sort_keys=True),
        json.dumps(review.get("limitations") or [], sort_keys=True),
    ]
    return "\n---\n".join(parts)


def input_hash_for(
    task: dict[str, Any], review: dict[str, Any], closing_note: str
) -> str:
    material = _bundle_input_material(task, review, closing_note)
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
    closing = read_closing_note(task_id, tasks_root)
    subjects: list[str] = []
    req_ids: list[str] = []
    for f in review.get("findings") or []:
        subj = str(f.get("subject") or "")
        if subj:
            subjects.append(subj)
        for rid in requirement_ids_for_finding(f):
            if rid not in req_ids:
                req_ids.append(rid)
    ih = input_hash_for(task, review, closing)
    bundle_id = f"{task_id.replace('/', '-')}--r{review_round}--{ih}"
    return ReviewBundle(
        bundle_id=bundle_id,
        task_id=task_id,
        review_round=review_round,
        head=str(review.get("head") or ""),
        cohort=cohort,
        expected_pass=expected_pass,
        adjudicated_defects=adjudicated or [],
        title=str(task.get("title") or ""),
        description_excerpt=_excerpt(str(task.get("description") or ""), 2000),
        stat=str(task.get("stat") or ""),
        closing_note_excerpt=_excerpt(closing, 3000),
        saved_review_pass=bool(review.get("pass"))
        if review.get("pass") is not None
        else None,
        saved_finding_subjects=subjects,
        saved_requirement_ids=req_ids,
        input_hash=ih,
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
        bundles.append(ReviewBundle(**raw))
    return doc, bundles
