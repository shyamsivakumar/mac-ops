"""Metrics for reviewer agreement scorecards."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from .board_io import read_task
from .requirements import requirement_ids_for_finding, requirement_ids_for_subject


@dataclass
class ShadowVerdict:
    pass_verdict: bool
    finding_subjects: list[str]
    requirement_ids: list[str]
    model: str
    repeat: int
    raw: str = ""
    error: bool = False


@dataclass
class BundleMetrics:
    bundle_id: str
    flip_rate: float | None
    adjacent_flip_count: int
    pass_flips: int  # alias: adjacent transitions for HTML compat
    repeats: int
    valid_repeats: int
    error_repeats: int
    incomplete: bool
    defect_recall: float | None
    false_block: bool | None
    recurring_requirements: list[str] = field(default_factory=list)


@dataclass
class ScorecardMetrics:
    bundle_count: int
    repeat_count: int
    flip_rate_overall: float | None
    bundles_with_any_flip: int
    bundles_incomplete: int
    defect_recall_overall: float | None
    defect_recall_denominator: int
    false_block_rate: float | None
    false_block_count: int
    clean_bundle_count: int
    clean_eligible_count: int
    recurring_requirements: list[tuple[str, int, list[int]]]
    cross_task_requirement_counts: list[tuple[str, int]]
    per_bundle: list[BundleMetrics]
    loop_median: float
    loop_p90: float
    worst_offenders: list[dict[str, Any]]


def wilson_upper_bound(successes: int, trials: int, z: float = 1.645) -> float | None:
    if trials <= 0:
        return None
    p = successes / trials
    denom = 1 + z * z / trials
    center = p + z * z / (2 * trials)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * trials)) / trials)
    return min(1.0, (center + margin) / denom)


def _pairwise_flip_rate(valid: list[ShadowVerdict]) -> tuple[float | None, int]:
    if len(valid) < 2:
        return None, 0
    pairs = 0
    disagree = 0
    for i in range(len(valid)):
        for j in range(i + 1, len(valid)):
            pairs += 1
            if valid[i].pass_verdict != valid[j].pass_verdict:
                disagree += 1
    return (disagree / pairs if pairs else None), disagree


def compute_bundle_metrics(
    bundle_id: str,
    verdicts: list[ShadowVerdict],
    *,
    expected_pass: bool | None,
    adjudicated_req_ids: list[str],
    saved_requirement_ids: list[str],
) -> BundleMetrics:
    valid = [v for v in verdicts if not v.error]
    error_repeats = sum(1 for v in verdicts if v.error)
    flip_rate, _disagree_pairs = _pairwise_flip_rate(valid)
    adjacent = sum(
        1
        for i in range(1, len(valid))
        if valid[i].pass_verdict != valid[i - 1].pass_verdict
    )
    incomplete = len(valid) < len(verdicts) or len(valid) < 2

    recall: float | None = None
    if adjudicated_req_ids and valid:
        caught: set[str] = set()
        for v in valid:
            caught.update(v.requirement_ids)
            for subj in v.finding_subjects:
                caught.update(requirement_ids_for_subject(subj))
        need = set(adjudicated_req_ids)
        recall = len(need & caught) / len(need) if need else None

    false_block: bool | None = None
    if expected_pass is True:
        if not valid:
            false_block = None
        else:
            false_block = any(not v.pass_verdict for v in valid)

    return BundleMetrics(
        bundle_id=bundle_id,
        flip_rate=flip_rate,
        adjacent_flip_count=adjacent,
        pass_flips=adjacent,
        repeats=len(verdicts),
        valid_repeats=len(valid),
        error_repeats=error_repeats,
        incomplete=incomplete,
        defect_recall=recall,
        false_block=false_block,
        recurring_requirements=saved_requirement_ids,
    )


def recurring_requirements_for_tasks(
    task_ids: list[str],
) -> tuple[list[tuple[str, int, list[int]]], list[tuple[str, int]]]:
    """Requirements appearing in >=2 distinct review rounds on the same task."""
    unique_tasks = sorted(set(task_ids))
    recurring: list[tuple[str, int, list[int]]] = []
    cross: Counter[str] = Counter()
    for tid in unique_tasks:
        task = read_task(tid)
        by_round: dict[int, set[str]] = defaultdict(set)
        for rev in task.get("reviews") or []:
            rnd = int(rev.get("round") or 0)
            for f in rev.get("findings") or []:
                for rid in requirement_ids_for_finding(f):
                    by_round[rnd].add(rid)
                    cross[rid] += 1
        rid_to_rounds: dict[str, set[int]] = defaultdict(set)
        for rnd, rids in by_round.items():
            for rid in rids:
                rid_to_rounds[rid].add(rnd)
        for rid, rounds in rid_to_rounds.items():
            if len(rounds) >= 2:
                recurring.append((rid, len(rounds), sorted(rounds)))
    recurring.sort(key=lambda x: (-x[1], x[0]))
    cross_list = [(rid, count) for rid, count in cross.most_common(12)]
    return recurring[:12], cross_list


def aggregate_scorecard(
    bundle_rows: list[tuple[Any, list[ShadowVerdict]]],
    *,
    loop_median: float,
    loop_p90: float,
    task_ids: list[str],
) -> ScorecardMetrics:
    per_bundle: list[BundleMetrics] = []
    flip_sum = 0.0
    flip_denom = 0
    bundles_with_flip = 0
    bundles_incomplete = 0
    recall_num = 0.0
    recall_den = 0
    false_blocks = 0
    clean_count = 0
    clean_eligible = 0

    for bundle, verdicts in bundle_rows:
        bm = compute_bundle_metrics(
            bundle.bundle_id,
            verdicts,
            expected_pass=bundle.expected_pass,
            adjudicated_req_ids=[d.requirement_id for d in bundle.adjudicated_defects],
            saved_requirement_ids=bundle.saved_requirement_ids,
        )
        per_bundle.append(bm)
        if bm.incomplete:
            bundles_incomplete += 1
        if bm.flip_rate is not None:
            flip_sum += bm.flip_rate
            flip_denom += 1
            if bm.flip_rate > 0:
                bundles_with_flip += 1
        if bm.defect_recall is not None:
            recall_num += bm.defect_recall
            recall_den += 1
        if bundle.expected_pass is True:
            clean_count += 1
            if bm.valid_repeats > 0:
                clean_eligible += 1
                if bm.false_block:
                    false_blocks += 1

    recurring, cross = recurring_requirements_for_tasks(task_ids)
    offenders = sorted(
        [b for b in per_bundle if b.flip_rate is not None],
        key=lambda b: (b.flip_rate or 0, b.adjacent_flip_count),
        reverse=True,
    )[:3]
    worst = [
        {
            "bundle_id": o.bundle_id,
            "flip_rate": o.flip_rate,
            "adjacent_flip_count": o.adjacent_flip_count,
            "valid_repeats": o.valid_repeats,
            "error_repeats": o.error_repeats,
            "defect_recall": o.defect_recall,
            "false_block": o.false_block,
        }
        for o in offenders
    ]

    overall_recall = recall_num / recall_den if recall_den else None
    false_rate = false_blocks / clean_eligible if clean_eligible else None

    return ScorecardMetrics(
        bundle_count=len(per_bundle),
        repeat_count=max((b.repeats for b in per_bundle), default=0),
        flip_rate_overall=flip_sum / flip_denom if flip_denom else None,
        bundles_with_any_flip=bundles_with_flip,
        bundles_incomplete=bundles_incomplete,
        defect_recall_overall=overall_recall,
        defect_recall_denominator=recall_den,
        false_block_rate=false_rate,
        false_block_count=false_blocks,
        clean_bundle_count=clean_count,
        clean_eligible_count=clean_eligible,
        recurring_requirements=recurring,
        cross_task_requirement_counts=cross,
        per_bundle=per_bundle,
        loop_median=loop_median,
        loop_p90=loop_p90,
        worst_offenders=worst,
    )
