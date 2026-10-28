"""Recompute scorecard metrics under ship-and-score pass rules from saved raw runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .bundles import ReviewBundle, load_manifest
from .history import compute_loop_stats
from .metrics import ShadowVerdict, aggregate_scorecard
from .requirements import requirement_ids_for_subject
from .scorecard import write_scorecard
from .shadow import _extract_json_verdict, _parse_verdict


def ship_and_score_pass_from_findings(findings: list[dict[str, Any]]) -> bool:
    """Match review.mustFix critical: only critical findings block."""
    for f in findings:
        if str(f.get("severity") or "").lower() == "critical":
            return False
    return True


def verdict_from_raw_entry(
    entry: dict[str, Any], *, model: str, repeat: int
) -> ShadowVerdict:
    if entry.get("error"):
        return ShadowVerdict(
            pass_verdict=False,
            finding_subjects=[],
            requirement_ids=[],
            model=model,
            repeat=repeat,
            raw=(entry.get("raw") or "")[:800],
            error=True,
        )
    raw = entry.get("raw") or ""
    parsed = _extract_json_verdict(raw)
    if parsed is None or "findings" not in parsed:
        v = _parse_verdict(raw, model, repeat)
        if not v.error:
            return ShadowVerdict(
                pass_verdict=v.pass_verdict,
                finding_subjects=v.finding_subjects,
                requirement_ids=v.requirement_ids,
                model=model,
                repeat=repeat,
                raw=v.raw,
                error=True,
            )
        subjects = [str(s) for s in (entry.get("subjects") or []) if s]
        req_ids: list[str] = []
        for s in subjects:
            for rid in requirement_ids_for_subject(s):
                if rid not in req_ids:
                    req_ids.append(rid)
        for rid in entry.get("requirement_ids") or []:
            rid_s = str(rid)
            if rid_s not in req_ids:
                req_ids.append(rid_s)
        return ShadowVerdict(
            pass_verdict=False,
            finding_subjects=subjects,
            requirement_ids=req_ids,
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
    findings = parsed.get("findings") or []
    if not isinstance(findings, list):
        return _parse_verdict(raw, model, repeat)
    subjects = [str(f.get("subject") or "") for f in findings if f.get("subject")]
    req_ids: list[str] = []
    for s in subjects:
        for rid in requirement_ids_for_subject(s):
            if rid not in req_ids:
                req_ids.append(rid)
    for rid in entry.get("requirement_ids") or []:
        if rid not in req_ids:
            req_ids.append(str(rid))
    return ShadowVerdict(
        pass_verdict=ship_and_score_pass_from_findings(findings),
        finding_subjects=subjects,
        requirement_ids=req_ids,
        model=model,
        repeat=repeat,
        raw=raw[:800],
        error=False,
    )


def rescore_from_scorecard(
    source: Path,
    manifest_path: Path,
    *,
    out_dir: Path,
    baseline_path: Path | None = None,
) -> dict[str, Any]:
    data = json.loads(source.read_text(encoding="utf-8"))
    raw_runs = data.get("raw_runs") or {}
    _, bundles = load_manifest(manifest_path)
    rows: list[tuple[ReviewBundle, list[ShadowVerdict]]] = []
    raw_out: dict[str, list] = {}
    for bundle in bundles:
        entries = raw_runs.get(bundle.bundle_id) or []
        verdicts = [
            verdict_from_raw_entry(
                e,
                model=str(e.get("model") or "?"),
                repeat=int(e.get("repeat") or i + 1),
            )
            for i, e in enumerate(entries)
        ]
        rows.append((bundle, verdicts))
        raw_out[bundle.bundle_id] = [
            {
                "pass": v.pass_verdict,
                "model": v.model,
                "repeat": v.repeat,
                "subjects": v.finding_subjects,
                "requirement_ids": v.requirement_ids,
                "error": v.error,
                "raw": v.raw,
                "rescore": True,
            }
            for v in verdicts
        ]
    loops = compute_loop_stats()
    metrics = aggregate_scorecard(
        rows,
        loop_median=loops.median_rounds,
        loop_p90=loops.p90_rounds,
        task_ids=[b.task_id for b in bundles],
    )
    baseline = None
    if baseline_path and baseline_path.is_file():
        try:
            base_data = json.loads(baseline_path.read_text(encoding="utf-8"))
            bm = base_data.get("metrics") or {}
            baseline = {
                "source": str(baseline_path),
                "generated_at": base_data.get("generated_at"),
                "review_policy": base_data.get("review_policy", "legacy"),
                "flip_rate_overall": bm.get("flip_rate_overall"),
                "defect_recall_overall": bm.get("defect_recall_overall"),
                "false_block_rate": bm.get("false_block_rate"),
                "false_block_count": bm.get("false_block_count"),
                "clean_eligible_count": bm.get("clean_eligible_count"),
                "loop_median": bm.get("loop_median"),
                "loop_p90": bm.get("loop_p90"),
            }
        except (OSError, json.JSONDecodeError):
            baseline = None
    write_scorecard(
        out_dir,
        metrics,
        raw_runs=raw_out,
        review_policy="board-rescore",
        baseline_metrics=baseline,
    )
    return {
        "flip_rate_overall": metrics.flip_rate_overall,
        "defect_recall_overall": metrics.defect_recall_overall,
        "false_block_rate": metrics.false_block_rate,
        "false_block_count": metrics.false_block_count,
        "clean_eligible_count": metrics.clean_eligible_count,
    }


def reaggregate_from_scorecard(
    source: Path,
    manifest_path: Path,
    *,
    out_dir: Path,
    baseline_path: Path | None = None,
) -> dict[str, Any]:
    """Recompute metrics from saved raw_runs (same replay receipt, updated rules)."""
    data = json.loads(source.read_text(encoding="utf-8"))
    raw_runs = data.get("raw_runs") or {}
    review_policy = str(data.get("review_policy") or "board")
    _, bundles = load_manifest(manifest_path)
    rows: list[tuple[ReviewBundle, list[ShadowVerdict]]] = []
    for bundle in bundles:
        entries = raw_runs.get(bundle.bundle_id) or []
        verdicts: list[ShadowVerdict] = []
        for i, entry in enumerate(entries):
            model = str(entry.get("model") or "?")
            repeat = int(entry.get("repeat") or i + 1)
            if entry.get("error"):
                verdicts.append(
                    ShadowVerdict(
                        pass_verdict=False,
                        finding_subjects=[],
                        requirement_ids=[],
                        model=model,
                        repeat=repeat,
                        raw=(entry.get("raw") or "")[:800],
                        error=True,
                    )
                )
                continue
            subjects = [str(s) for s in (entry.get("subjects") or []) if s]
            req_ids: list[str] = []
            for s in subjects:
                for rid in requirement_ids_for_subject(s):
                    if rid not in req_ids:
                        req_ids.append(rid)
            verdicts.append(
                ShadowVerdict(
                    pass_verdict=bool(entry.get("pass")),
                    finding_subjects=subjects,
                    requirement_ids=req_ids,
                    model=model,
                    repeat=repeat,
                    raw=(entry.get("raw") or "")[:800],
                    error=False,
                )
            )
        rows.append((bundle, verdicts))
    loops = compute_loop_stats()
    metrics = aggregate_scorecard(
        rows,
        loop_median=loops.median_rounds,
        loop_p90=loops.p90_rounds,
        task_ids=[b.task_id for b in bundles],
    )
    baseline = None
    if baseline_path and baseline_path.is_file():
        try:
            base_data = json.loads(baseline_path.read_text(encoding="utf-8"))
            bm = base_data.get("metrics") or {}
            baseline = {
                "source": str(baseline_path),
                "generated_at": base_data.get("generated_at"),
                "review_policy": base_data.get("review_policy", "legacy"),
                "flip_rate_overall": bm.get("flip_rate_overall"),
                "defect_recall_overall": bm.get("defect_recall_overall"),
                "false_block_rate": bm.get("false_block_rate"),
                "false_block_count": bm.get("false_block_count"),
                "clean_eligible_count": bm.get("clean_eligible_count"),
                "loop_median": bm.get("loop_median"),
                "loop_p90": bm.get("loop_p90"),
            }
        except (OSError, json.JSONDecodeError):
            baseline = None
    write_scorecard(
        out_dir,
        metrics,
        raw_runs=raw_runs,
        review_policy=review_policy,
        reviewer_instructions_sha256=data.get("reviewer_instructions_sha256"),
        baseline_metrics=baseline,
    )
    return {
        "flip_rate_overall": metrics.flip_rate_overall,
        "defect_recall_overall": metrics.defect_recall_overall,
        "false_block_rate": metrics.false_block_rate,
        "false_block_count": metrics.false_block_count,
        "clean_eligible_count": metrics.clean_eligible_count,
    }
