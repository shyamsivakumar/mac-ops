"""CLI for reviewer agreement audit (MO-10)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .board_io import read_reviewer_instructions
from .bundles import default_seed_bundles, bundles_kept_from, load_manifest, write_manifest
from .history import compute_loop_stats
from .metrics import aggregate_scorecard
from .retrospective import summarize_retrospective_flips
from .scorecard import write_scorecard


def _pkg_manifest() -> Path:
    return Path(__file__).resolve().parent / "manifest.json"


def cmd_freeze(args: argparse.Namespace) -> int:
    out = Path(args.out)
    bundles = default_seed_bundles()
    bundles += bundles_kept_from(out, bundles)
    write_manifest(out, bundles)
    print(f"Wrote {len(bundles)} bundles to {out}")
    return 0


def _load_baseline_metrics(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    metrics = data.get("metrics")
    if not isinstance(metrics, dict):
        return None
    return {
        "source": str(path),
        "generated_at": data.get("generated_at"),
        "review_policy": data.get("review_policy", "legacy"),
        "flip_rate_overall": metrics.get("flip_rate_overall"),
        "defect_recall_overall": metrics.get("defect_recall_overall"),
        "false_block_rate": metrics.get("false_block_rate"),
        "false_block_count": metrics.get("false_block_count"),
        "clean_eligible_count": metrics.get("clean_eligible_count"),
        "loop_median": metrics.get("loop_median"),
        "loop_p90": metrics.get("loop_p90"),
    }


def cmd_scorecard(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        manifest_path = _pkg_manifest()
    _, bundles = load_manifest(manifest_path)
    if args.limit:
        bundles = bundles[: args.limit]
    loops = compute_loop_stats()
    review_policy = args.review_policy
    reviewer_instructions: str | None = None
    if review_policy == "board":
        reviewer_instructions = read_reviewer_instructions()
    instr_hash = (
        hashlib.sha256(reviewer_instructions.encode("utf-8")).hexdigest()[:16]
        if reviewer_instructions
        else None
    )
    baseline = (
        _load_baseline_metrics(Path(args.baseline_scorecard))
        if args.baseline_scorecard
        else None
    )
    raw_runs: dict[str, list] = {}
    rows = []
    for i, bundle in enumerate(bundles):
        print(f"[{i + 1}/{len(bundles)}] shadow replay {bundle.bundle_id}", flush=True)
        if args.deterministic:
            from .shadow import replay_bundle

            verdicts = replay_bundle(
                bundle,
                repeats=args.repeats,
                use_models=False,
                review_policy=review_policy,
                reviewer_instructions=reviewer_instructions,
            )
        else:
            from .shadow import replay_bundle

            verdicts = replay_bundle(
                bundle,
                repeats=args.repeats,
                use_models=True,
                use_heavy=args.heavy,
                bundle_index=i,
                review_policy=review_policy,
                reviewer_instructions=reviewer_instructions,
            )
        rows.append((bundle, verdicts))
        raw_runs[bundle.bundle_id] = [
            {
                "pass": v.pass_verdict,
                "model": v.model,
                "repeat": v.repeat,
                "subjects": v.finding_subjects,
                "requirement_ids": v.requirement_ids,
                "error": v.error,
                "raw": v.raw,
            }
            for v in verdicts
        ]
    metrics = aggregate_scorecard(
        rows,
        loop_median=loops.median_rounds,
        loop_p90=loops.p90_rounds,
        task_ids=[b.task_id for b in bundles],
    )
    retro = summarize_retrospective_flips([b.task_id for b in bundles])
    judge_samples: dict[str, Any] = {}
    if not args.deterministic and args.judge_samples and bundles:
        from .judge import judge_bundle_layer

        sample = bundles[: min(3, len(bundles))]
        for b in sample:
            judge_samples[b.bundle_id] = {
                "gpt-6.1": judge_bundle_layer(b.closing_note_excerpt, "gpt-6.1"),
                "claude-opus": judge_bundle_layer(
                    b.closing_note_excerpt, "claude-opus"
                ),
            }
    out_dir = Path(args.out)
    write_scorecard(
        out_dir,
        metrics,
        raw_runs=raw_runs,
        retrospective=retro,
        judge_samples=judge_samples,
        review_policy=review_policy,
        reviewer_instructions_sha256=instr_hash,
        baseline_metrics=baseline,
    )
    print(render_summary(metrics))
    return 0


def cmd_rescore(args: argparse.Namespace) -> int:
    from .rescore import rescore_from_scorecard

    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        manifest_path = _pkg_manifest()
    summary = rescore_from_scorecard(
        Path(args.source),
        manifest_path,
        out_dir=Path(args.out),
        baseline_path=Path(args.baseline_scorecard)
        if args.baseline_scorecard
        else None,
    )
    print(
        "Rescore (ship-and-score pass on saved shadow findings): "
        f"flip {summary['flip_rate_overall']:.1%}, "
        f"recall {summary['defect_recall_overall']}, "
        f"false blocks {summary['false_block_count']}/{summary['clean_eligible_count']} "
        f"({summary['false_block_rate']:.1%})"
    )
    return 0


def cmd_reaggregate(args: argparse.Namespace) -> int:
    from .rescore import reaggregate_from_scorecard

    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        manifest_path = _pkg_manifest()
    summary = reaggregate_from_scorecard(
        Path(args.source),
        manifest_path,
        out_dir=Path(args.out),
        baseline_path=Path(args.baseline_scorecard)
        if args.baseline_scorecard
        else None,
    )
    print(
        "Reaggregate: "
        f"flip {summary['flip_rate_overall']:.1%}, "
        f"recall {summary['defect_recall_overall']}, "
        f"false blocks {summary['false_block_count']}/{summary['clean_eligible_count']} "
        f"({summary['false_block_rate']:.1%})"
    )
    return 0


def render_summary(metrics) -> str:
    flip = (
        f"{metrics.flip_rate_overall:.1%}"
        if metrics.flip_rate_overall is not None
        else "n/a"
    )
    return (
        f"Scorecard: {metrics.bundle_count} bundles, "
        f"pairwise flip {flip}, "
        f"incomplete {metrics.bundles_incomplete}, "
        f"recall {metrics.defect_recall_overall}, "
        f"false blocks {metrics.false_block_count}/{metrics.clean_eligible_count}, "
        f"loops median/p90 {metrics.loop_median:.1f}/{metrics.loop_p90:.1f}"
    )


def cmd_loops(args: argparse.Namespace) -> int:
    loops = compute_loop_stats()
    print(json.dumps(loops.__dict__, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reviewer_audit", description="MO-10 reviewer agreement tool"
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_freeze = sub.add_parser(
        "freeze", help="Build frozen benchmark manifest from board archive"
    )
    p_freeze.add_argument(
        "--out",
        default=str(_pkg_manifest()),
        help="Manifest JSON path",
    )
    p_freeze.set_defaults(func=cmd_freeze)

    p_score = sub.add_parser(
        "scorecard", help="Run shadow replay and write weekly scorecard"
    )
    p_score.add_argument("--manifest", default=str(_pkg_manifest()))
    p_score.add_argument("--out", required=True, help="Report directory")
    p_score.add_argument("--repeats", type=int, default=5)
    p_score.add_argument("--limit", type=int, default=0, help="Max bundles (0=all)")
    p_score.add_argument(
        "--deterministic",
        action="store_true",
        help="Use saved review only (smoke test, no LLM)",
    )
    p_score.add_argument(
        "--judge-samples",
        action="store_true",
        help="Run mixed-model judge on first 3 bundles (slow)",
    )
    p_score.add_argument(
        "--heavy",
        action="store_true",
        help="Route each LLM call through heavy --review",
    )
    p_score.add_argument(
        "--review-policy",
        choices=("board", "legacy"),
        default="board",
        help="board=current reviewer.instructions (default); legacy=MO-10 major/critical gate",
    )
    p_score.add_argument(
        "--baseline-scorecard",
        default="",
        help="Prior scorecard.json for before/after comparison in the report",
    )
    p_score.set_defaults(func=cmd_scorecard)

    p_rescore = sub.add_parser(
        "rescore",
        help="Recompute metrics from a prior scorecard.json under ship-and-score pass rules",
    )
    p_rescore.add_argument(
        "source",
        help="Prior scorecard.json (e.g. MO-10 baseline run)",
    )
    p_rescore.add_argument("--manifest", default=str(_pkg_manifest()))
    p_rescore.add_argument("--out", required=True, help="Report directory")
    p_rescore.add_argument(
        "--baseline-scorecard",
        default="",
        help="Include before/after vs this baseline file",
    )
    p_rescore.set_defaults(func=cmd_rescore)

    p_reagg = sub.add_parser(
        "reaggregate",
        help="Recompute scorecard metrics from saved raw_runs (same LLM receipt)",
    )
    p_reagg.add_argument("source", help="scorecard.json with raw_runs")
    p_reagg.add_argument("--manifest", default=str(_pkg_manifest()))
    p_reagg.add_argument("--out", required=True)
    p_reagg.add_argument("--baseline-scorecard", default="")
    p_reagg.set_defaults(func=cmd_reaggregate)

    p_loops = sub.add_parser("loops", help="Print board review-round percentiles")
    p_loops.set_defaults(func=cmd_loops)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
