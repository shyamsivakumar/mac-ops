"""Retrospective flip signals from saved board reviews."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .board_io import read_closing_note, read_task
from .bundles import (
    _closing_note_for_head,
    input_hash_for_material,
    saved_proof_from_review,
)


@dataclass
class SameInputFlip:
    task_id: str
    input_hash: str
    rounds: list[int]
    passes: list[bool]
    flip_count: int


def review_input_hash(
    task: dict[str, Any], review: dict[str, Any], closing: str
) -> str:
    head = str(review.get("head") or "")
    agent_note = _closing_note_for_head(closing, head)
    material = "\n---\n".join(
        [
            str(task.get("id", "")),
            str(review.get("round", "")),
            head,
            str(task.get("description") or ""),
            saved_proof_from_review(review),
            agent_note,
            str(review.get("by") or ""),
        ]
    )
    return input_hash_for_material(material)


def same_input_flips_for_task(task_id: str) -> list[SameInputFlip]:
    task = read_task(task_id)
    closing = read_closing_note(task_id)
    reviews = task.get("reviews") or []
    by_hash: dict[str, list[dict[str, Any]]] = {}
    for rev in reviews:
        ih = review_input_hash(task, rev, closing)
        by_hash.setdefault(ih, []).append(rev)
    out: list[SameInputFlip] = []
    for ih, group in by_hash.items():
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda r: r.get("round") or 0)
        passes = [bool(r.get("pass")) for r in group]
        flips = sum(1 for i in range(1, len(passes)) if passes[i] != passes[i - 1])
        if flips == 0:
            continue
        out.append(
            SameInputFlip(
                task_id=task_id,
                input_hash=ih,
                rounds=[int(r.get("round") or 0) for r in group],
                passes=passes,
                flip_count=flips,
            )
        )
    return out


def summarize_retrospective_flips(task_ids: list[str]) -> dict[str, Any]:
    unique_tasks = sorted(set(task_ids))
    rows: list[SameInputFlip] = []
    for tid in unique_tasks:
        rows.extend(same_input_flips_for_task(tid))
    total_transitions = 0
    total_flips = 0
    for row in rows:
        total_transitions += len(row.passes) - 1
        total_flips += row.flip_count
    return {
        "scope": "same full input identity (description, round proof, agent note when commit matches, reviewer)",
        "note": "Not same-commit-only; commit-only grouping is intentionally excluded.",
        "groups_with_flips": len(rows),
        "transition_count": total_transitions,
        "flip_count": total_flips,
        "flip_rate": total_flips / total_transitions if total_transitions else 0.0,
        "examples": [
            {
                "task_id": r.task_id,
                "input_hash": r.input_hash,
                "rounds": r.rounds,
                "passes": r.passes,
            }
            for r in rows[:5]
        ],
    }
