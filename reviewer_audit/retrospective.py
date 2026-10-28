"""Retrospective flip signals from saved board reviews at unchanged commits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .board_io import read_closing_note, read_task
from .bundles import input_hash_for


@dataclass
class SameInputFlip:
    task_id: str
    head: str
    input_hash: str
    rounds: list[int]
    passes: list[bool]
    flip_count: int


def same_input_flips_for_task(task_id: str) -> list[SameInputFlip]:
    task = read_task(task_id)
    closing = read_closing_note(task_id)
    reviews = task.get("reviews") or []
    by_head: dict[str, list[dict[str, Any]]] = {}
    for rev in reviews:
        head = str(rev.get("head") or "")
        if not head:
            continue
        by_head.setdefault(head, []).append(rev)
    out: list[SameInputFlip] = []
    for head, group in by_head.items():
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda r: r.get("round") or 0)
        passes = [bool(r.get("pass")) for r in group]
        flips = sum(1 for i in range(1, len(passes)) if passes[i] != passes[i - 1])
        if flips == 0 and all(p == passes[0] for p in passes):
            # Same verdict every round at this commit — still note for stability
            continue
        ih = input_hash_for(task, group[0], closing)
        out.append(
            SameInputFlip(
                task_id=task_id,
                head=head,
                input_hash=ih,
                rounds=[int(r.get("round") or 0) for r in group],
                passes=passes,
                flip_count=flips,
            )
        )
    return out


def summarize_retrospective_flips(task_ids: list[str]) -> dict[str, Any]:
    rows: list[SameInputFlip] = []
    for tid in task_ids:
        rows.extend(same_input_flips_for_task(tid))
    total_transitions = 0
    total_flips = 0
    for tid in task_ids:
        task = read_task(tid)
        by_head: dict[str, list] = {}
        for rev in task.get("reviews") or []:
            head = str(rev.get("head") or "")
            if head:
                by_head.setdefault(head, []).append(rev)
        for group in by_head.values():
            if len(group) < 2:
                continue
            group = sorted(group, key=lambda r: r.get("round") or 0)
            passes = [bool(r.get("pass")) for r in group]
            total_transitions += len(passes) - 1
            total_flips += sum(
                1 for i in range(1, len(passes)) if passes[i] != passes[i - 1]
            )
    return {
        "groups_with_flips": len(rows),
        "transition_count": total_transitions,
        "flip_count": total_flips,
        "flip_rate": total_flips / total_transitions if total_transitions else 0.0,
        "examples": [
            {
                "task_id": r.task_id,
                "rounds": r.rounds,
                "passes": r.passes,
                "head": r.head[:12],
            }
            for r in rows[:5]
        ],
    }
