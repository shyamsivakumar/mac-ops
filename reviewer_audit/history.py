"""Loop statistics from board task history."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

from .board_io import iter_tasks_with_reviews


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(ordered) - 1)
    if f == c:
        return float(ordered[f])
    return float(ordered[f] + (ordered[c] - ordered[f]) * (k - f))


@dataclass
class LoopStats:
    task_count: int
    median_rounds: float
    p90_rounds: float
    max_rounds: int
    by_repo: dict[str, dict[str, float]]


def compute_loop_stats(tasks: list[dict[str, Any]] | None = None) -> LoopStats:
    tasks = tasks if tasks is not None else iter_tasks_with_reviews()
    rounds: list[float] = []
    by_repo: dict[str, list[float]] = {}
    for task in tasks:
        revs = task.get("reviews") or []
        if not revs:
            continue
        n = float(len(revs))
        rounds.append(n)
        repo = str(task.get("repo") or task.get("id", "").split("/")[0])
        by_repo.setdefault(repo, []).append(n)
    repo_summary = {
        repo: {
            "median": statistics.median(vals) if vals else 0.0,
            "p90": _percentile(vals, 90),
            "count": float(len(vals)),
        }
        for repo, vals in sorted(by_repo.items())
    }
    return LoopStats(
        task_count=len(rounds),
        median_rounds=statistics.median(rounds) if rounds else 0.0,
        p90_rounds=_percentile(rounds, 90),
        max_rounds=int(max(rounds)) if rounds else 0,
        by_repo=repo_summary,
    )
