"""Retrospective flip signals from saved board reviews."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .board_io import (
    git_diff_base_to_head,
    read_closing_note,
    read_task,
    task_repo_root,
)
from .bundles import (
    input_hash_for_material,
    resolve_review_base,
    submitted_review_input_material,
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
    diff_base = resolve_review_base(task, review)
    repo_root = task_repo_root(task)
    stat = ""
    if repo_root and diff_base and head:
        stat, _patch = git_diff_base_to_head(repo_root, diff_base, head)
    material = submitted_review_input_material(
        task,
        review,
        closing,
        diff_base=diff_base,
        stat=stat,
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
        "scope": (
            "submitted review input (task brief, diff base+head, diff stat, "
            "commit-scoped agent note, reviewer model) — excludes round number "
            "and saved verdict text"
        ),
        "groups_with_flips": len(rows),
        "transition_count": total_transitions,
        "flip_count": total_flips,
        "flip_rate": total_flips / total_transitions if total_transitions else None,
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
