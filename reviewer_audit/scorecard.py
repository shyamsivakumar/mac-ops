"""Weekly reviewer agreement scorecard (HTML + JSON)."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .metrics import ScorecardMetrics


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1%}"


def render_markdown(
    metrics: ScorecardMetrics,
    *,
    generated_at: str | None = None,
    retrospective: dict[str, Any] | None = None,
) -> str:
    ts = generated_at or datetime.now(timezone.utc).isoformat()
    lines = [
        "# Reviewer agreement and loop scorecard",
        "",
        f"Generated: {ts}",
        "",
        "## Summary",
        "",
        f"- Bundles scored: **{metrics.bundle_count}** ({metrics.repeat_count} shadow repeats each)",
        f"- Pairwise flip rate (mean across bundles with ≥2 valid repeats): **{_fmt_pct(metrics.flip_rate_overall)}**",
        f"- Bundles with any pass/fail disagreement: **{metrics.bundles_with_any_flip}**",
        f"- Bundles with incomplete repeats (errors or <2 valid): **{metrics.bundles_incomplete}**",
    ]
    if metrics.defect_recall_overall is not None:
        lines.append(
            f"- Defect recall (adjudicated requirements, mean): **{metrics.defect_recall_overall:.1%}** "
            f"(n={metrics.defect_recall_denominator})"
        )
    if metrics.false_block_rate is not None:
        lines.append(
            f"- False blocks on clean bundles: **{metrics.false_block_count}/{metrics.clean_eligible_count}** "
            f"eligible ({metrics.false_block_rate:.1%})"
        )
    lines.extend(
        [
            f"- Board history review rounds — median: **{metrics.loop_median:.1f}**, p90: **{metrics.loop_p90:.1f}**",
            "",
        ]
    )
    if retrospective:
        lines.extend(
            [
                "## Retrospective same-input flips (saved reviews)",
                "",
                f"- Scope: {retrospective.get('scope', '')}",
                f"- Groups with pass/fail changes: **{retrospective.get('groups_with_flips', 0)}**",
                f"- Adjacent transition flip rate: **{retrospective.get('flip_rate', 0):.1%}** "
                f"({retrospective.get('flip_count', 0)}/{retrospective.get('transition_count', 0)} transitions)",
                "",
            ]
        )
    lines.extend(
        [
            "## Three worst offenders (shadow pairwise flip rate)",
            "",
        ]
    )
    for w in metrics.worst_offenders:
        lines.append(
            f"- `{w['bundle_id']}`: flip rate {w['flip_rate']:.0%}, "
            f"adjacent transitions {w.get('adjacent_flip_count', w.get('pass_flips', 0))}, "
            f"valid/error repeats {w.get('valid_repeats', '?')}/{w.get('error_repeats', '?')}, "
            f"recall {w.get('defect_recall')}, false_block {w.get('false_block')}"
        )
    lines.extend(
        [
            "",
            "## Recurring requirement IDs (same task, ≥2 review rounds)",
            "",
        ]
    )
    for rid, round_count, rounds in metrics.recurring_requirements[:10]:
        lines.append(f"- `{rid}`: {round_count} rounds {rounds}")
    lines.extend(
        [
            "",
            "## Cross-task requirement prevalence (saved reviews, top IDs)",
            "",
        ]
    )
    for rid, count in metrics.cross_task_requirement_counts[:10]:
        lines.append(f"- `{rid}`: {count} saved-review hits")
    lines.extend(["", "## Per bundle", ""])
    for b in metrics.per_bundle:
        flip_s = _fmt_pct(b.flip_rate)
        incomplete = " incomplete" if b.incomplete else ""
        lines.append(
            f"- `{b.bundle_id}`: flip {flip_s}, adjacent {b.adjacent_flip_count}, "
            f"valid {b.valid_repeats}/{b.repeats}{incomplete}, "
            f"recall {b.defect_recall}, false_block {b.false_block}"
        )
    lines.append("")
    lines.append("_Advisory scorecard — does not gate merges (LMW-25 / MO-10)._")
    return "\n".join(lines)


def render_html(metrics: ScorecardMetrics, *, generated_at: str | None = None) -> str:
    ts = html.escape(generated_at or datetime.now(timezone.utc).isoformat())
    rows = "".join(
        f"<tr><td>{html.escape(b.bundle_id)}</td>"
        f"<td>{_fmt_pct(b.flip_rate)}</td>"
        f"<td>{b.adjacent_flip_count}</td>"
        f"<td>{b.valid_repeats}/{b.repeats}</td>"
        f"<td>{b.defect_recall if b.defect_recall is not None else '—'}</td>"
        f"<td>{b.false_block if b.false_block is not None else '—'}</td></tr>"
        for b in metrics.per_bundle
    )
    worst = "".join(
        f"<li><code>{html.escape(w['bundle_id'])}</code> — pairwise flip {w['flip_rate']:.0%}, "
        f"{w.get('adjacent_flip_count', w.get('pass_flips', 0))} adjacent transitions</li>"
        for w in metrics.worst_offenders
    )
    recall = (
        f"{metrics.defect_recall_overall:.1%} (n={metrics.defect_recall_denominator})"
        if metrics.defect_recall_overall is not None
        else "n/a"
    )
    false_line = (
        f"{metrics.false_block_count}/{metrics.clean_eligible_count} "
        f"({metrics.false_block_rate:.1%})"
        if metrics.false_block_rate is not None
        else "n/a"
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Reviewer agreement scorecard</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: left; }}
th {{ background: #f4f4f4; }}
.note {{ color: #555; font-size: 0.95rem; }}
</style>
</head>
<body>
<h1>Reviewer agreement and loop scorecard</h1>
<p class="note">Generated {ts}. Advisory only — never blocks merge.</p>
<h2>Summary</h2>
<ul>
<li>Bundles: {metrics.bundle_count} × {metrics.repeat_count} shadow repeats (mixed models)</li>
<li>Mean pairwise flip rate: <strong>{_fmt_pct(metrics.flip_rate_overall)}</strong></li>
<li>Bundles with any disagreement: {metrics.bundles_with_any_flip}; incomplete: {metrics.bundles_incomplete}</li>
<li>Defect recall (adjudicated): <strong>{recall}</strong></li>
<li>False blocks on clean bundles (valid repeats only): <strong>{false_line}</strong></li>
<li>Board review rounds — median {metrics.loop_median:.1f}, p90 {metrics.loop_p90:.1f}</li>
</ul>
<h2>Three worst offenders</h2>
<ul>{worst}</ul>
<h2>All bundles</h2>
<table>
<thead><tr><th>Bundle</th><th>Pairwise flip</th><th>Adjacent transitions</th><th>Valid repeats</th><th>Defect recall</th><th>False block</th></tr></thead>
<tbody>{rows}</tbody>
</table>
</body>
</html>
"""


def write_scorecard(
    out_dir: Path,
    metrics: ScorecardMetrics,
    *,
    raw_runs: dict[str, Any] | None = None,
    retrospective: dict[str, Any] | None = None,
    judge_samples: dict[str, Any] | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    (out_dir / "report.md").write_text(
        render_markdown(metrics, generated_at=ts, retrospective=retrospective),
        encoding="utf-8",
    )
    (out_dir / "index.html").write_text(
        render_html(metrics, generated_at=ts), encoding="utf-8"
    )
    payload: dict[str, Any] = {
        "generated_at": ts,
        "metrics": {
            "bundle_count": metrics.bundle_count,
            "repeat_count": metrics.repeat_count,
            "flip_rate_overall": metrics.flip_rate_overall,
            "bundles_with_any_flip": metrics.bundles_with_any_flip,
            "bundles_incomplete": metrics.bundles_incomplete,
            "defect_recall_overall": metrics.defect_recall_overall,
            "false_block_rate": metrics.false_block_rate,
            "false_block_count": metrics.false_block_count,
            "clean_eligible_count": metrics.clean_eligible_count,
            "loop_median": metrics.loop_median,
            "loop_p90": metrics.loop_p90,
            "worst_offenders": metrics.worst_offenders,
            "recurring_requirements": metrics.recurring_requirements,
            "cross_task_requirement_counts": metrics.cross_task_requirement_counts,
        },
        "per_bundle": [
            {
                "bundle_id": b.bundle_id,
                "flip_rate": b.flip_rate,
                "adjacent_flip_count": b.adjacent_flip_count,
                "valid_repeats": b.valid_repeats,
                "error_repeats": b.error_repeats,
                "incomplete": b.incomplete,
                "defect_recall": b.defect_recall,
                "false_block": b.false_block,
            }
            for b in metrics.per_bundle
        ],
    }
    if raw_runs:
        payload["raw_runs"] = raw_runs
    if retrospective:
        payload["retrospective_same_input_flips"] = retrospective
    if judge_samples:
        payload["mixed_model_judge_samples"] = judge_samples
    (out_dir / "scorecard.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
