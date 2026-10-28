"""Metrics for reviewer agreement scorecards."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .requirements import requirement_ids_for_subject


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
    flip_rate: float
    pass_flips: int
    repeats: int
    defect_recall: float | None
    false_block: bool | None
    recurring_requirements: list[str] = field(default_factory=list)


@dataclass
class ScorecardMetrics:
    bundle_count: int
    repeat_count: int
    flip_rate_overall: float
    bundles_with_any_flip: int
    defect_recall_overall: float | None
    defect_recall_denominator: int
    false_block_rate: float | None
    false_block_count: int
    clean_bundle_count: int
    recurring_requirements: list[tuple[str, int]]
    per_bundle: list[BundleMetrics]
    loop_median: float
    loop_p90: float
    worst_offenders: list[dict[str, Any]]


def _req_ids_from_subjects(subjects: list[str]) -> list[str]:
    out: list[str] = []
    for s in subjects:
        for rid in requirement_ids_for_subject(s):
            if rid not in out:
                out.append(rid)
    return out


def cohen_kappa(a: list[bool], b: list[bool]) -> float | None:
    if len(a) != len(b) or not a:
        return None
    n = len(a)
    agree = sum(1 for x, y in zip(a, b) if x == y)
    pa = agree / n
    p_yes_a = sum(a) / n
    p_yes_b = sum(b) / n
    pe = p_yes_a * p_yes_b + (1 - p_yes_a) * (1 - p_yes_b)
    if math.isclose(1 - pe, 0.0):
        return None
    return (pa - pe) / (1 - pe)


def wilson_upper_bound(successes: int, trials: int, z: float = 1.645) -> float | None:
    if trials <= 0:
        return None
    p = successes / trials
    denom = 1 + z * z / trials
    center = p + z * z / (2 * trials)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * trials)) / trials)
    return min(1.0, (center + margin) / denom)


def compute_bundle_metrics(
    bundle_id: str,
    verdicts: list[ShadowVerdict],
    *,
    expected_pass: bool | None,
    adjudicated_req_ids: list[str],
    saved_requirement_ids: list[str],
) -> BundleMetrics:
    passes = [v.pass_verdict for v in verdicts if not v.error]
    flip_count = 0
    if len(passes) > 1:
        first = passes[0]
        flip_count = sum(1 for p in passes[1:] if p != first)
    valid = [v for v in verdicts if not v.error]
    if len(valid) > 1:
        uniq = {v.pass_verdict for v in valid}
        pair_flips = 1 if len(uniq) > 1 else 0
    else:
        pair_flips = 0
    flip_rate = pair_flips if len(valid) > 1 else 0.0

    recall: float | None = None
    if adjudicated_req_ids and verdicts:
        caught: set[str] = set()
        for v in verdicts:
            if v.error:
                continue
            caught.update(v.requirement_ids)
        need = set(adjudicated_req_ids)
        recall = len(need & caught) / len(need) if need else None

    false_block: bool | None = None
    if expected_pass is True and verdicts:
        false_block = any(not v.pass_verdict and not v.error for v in verdicts)

    return BundleMetrics(
        bundle_id=bundle_id,
        flip_rate=flip_rate,
        pass_flips=flip_count,
        repeats=len(verdicts),
        defect_recall=recall,
        false_block=false_block,
        recurring_requirements=saved_requirement_ids,
    )


def aggregate_scorecard(
    bundle_rows: list[tuple[Any, list[ShadowVerdict]]],
    *,
    loop_median: float,
    loop_p90: float,
) -> ScorecardMetrics:
    per_bundle: list[BundleMetrics] = []
    flip_sum = 0.0
    flip_denom = 0
    bundles_with_flip = 0
    recall_num = 0.0
    recall_den = 0
    false_blocks = 0
    clean_count = 0
    req_counter: Counter[str] = Counter()

    for bundle, verdicts in bundle_rows:
        bm = compute_bundle_metrics(
            bundle.bundle_id,
            verdicts,
            expected_pass=bundle.expected_pass,
            adjudicated_req_ids=[d.requirement_id for d in bundle.adjudicated_defects],
            saved_requirement_ids=bundle.saved_requirement_ids,
        )
        per_bundle.append(bm)
        if bm.repeats > 1:
            flip_sum += bm.flip_rate
            flip_denom += 1
        if bm.pass_flips > 0:
            bundles_with_flip += 1
        if bm.defect_recall is not None:
            recall_num += bm.defect_recall
            recall_den += 1
        if bundle.expected_pass is True:
            clean_count += 1
            if bm.false_block:
                false_blocks += 1
        for rid in bundle.saved_requirement_ids:
            req_counter[rid] += 1

    recurring = req_counter.most_common(12)
    offenders = sorted(
        per_bundle,
        key=lambda b: (b.flip_rate, b.pass_flips, -(b.defect_recall or 0)),
        reverse=True,
    )[:3]
    worst = [
        {
            "bundle_id": o.bundle_id,
            "flip_rate": o.flip_rate,
            "pass_flips": o.pass_flips,
            "defect_recall": o.defect_recall,
            "false_block": o.false_block,
        }
        for o in offenders
    ]

    overall_recall = recall_num / recall_den if recall_den else None
    false_rate = false_blocks / clean_count if clean_count else None

    return ScorecardMetrics(
        bundle_count=len(per_bundle),
        repeat_count=max((b.repeats for b in per_bundle), default=0),
        flip_rate_overall=flip_sum / flip_denom if flip_denom else 0.0,
        bundles_with_any_flip=bundles_with_flip,
        defect_recall_overall=overall_recall,
        defect_recall_denominator=recall_den,
        false_block_rate=false_rate,
        false_block_count=false_blocks,
        clean_bundle_count=clean_count,
        recurring_requirements=recurring,
        per_bundle=per_bundle,
        loop_median=loop_median,
        loop_p90=loop_p90,
        worst_offenders=worst,
    )
