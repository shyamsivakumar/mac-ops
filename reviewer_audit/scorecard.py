"""Weekly reviewer agreement scorecard (HTML + JSON)."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .metrics import ScorecardMetrics


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
        f"- Same-input flip rate (mean across bundles): **{metrics.flip_rate_overall:.1%}**",
        f"- Bundles with any pass/fail flip: **{metrics.bundles_with_any_flip}**",
    ]
    if metrics.defect_recall_overall is not None:
        lines.append(
            f"- Defect recall (adjudicated requirements, mean): **{metrics.defect_recall_overall:.1%}** "
            f"(n={metrics.defect_recall_denominator})"
        )
    if metrics.false_block_rate is not None:
        lines.append(
            f"- False blocks on clean bundles: **{metrics.false_block_count}/{metrics.clean_bundle_count}** "
            f"({metrics.false_block_rate:.1%})"
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
                "## Retrospective same-commit flips (saved reviews)",
                "",
                f"- Groups with pass/fail changes at fixed commit: **{retrospective.get('groups_with_flips', 0)}**",
                f"- Transition flip rate: **{retrospective.get('flip_rate', 0):.1%}** "
                f"({retrospective.get('flip_count', 0)}/{retrospective.get('transition_count', 0)} transitions)",
                "",
            ]
        )
    lines.extend(
        [
            "## Three worst offenders (shadow flip / instability)",
            "",
        ]
    )
    for w in metrics.worst_offenders:
        lines.append(
            f"- `{w['bundle_id']}`: flip rate {w['flip_rate']:.0%}, "
            f"flips {w['pass_flips']}, recall {w.get('defect_recall')}, false_block {w.get('false_block')}"
        )
    lines.extend(["", "## Recurring requirement IDs (saved reviews in cohort)", ""])
    for rid, count in metrics.recurring_requirements[:10]:
        lines.append(f"- `{rid}`: {count} bundles")
    lines.extend(["", "## Per bundle", ""])
    for b in metrics.per_bundle:
        lines.append(
            f"- `{b.bundle_id}`: flip {b.flip_rate:.0%}, recall {b.defect_recall}, false_block {b.false_block}"
        )
    lines.append("")
    lines.append("_Advisory scorecard — does not gate merges (LMW-25 / MO-10)._")
    return "\n".join(lines)


def render_html(metrics: ScorecardMetrics, *, generated_at: str | None = None) -> str:
    ts = html.escape(generated_at or datetime.now(timezone.utc).isoformat())
    rows = "".join(
        f"<tr><td>{html.escape(b.bundle_id)}</td>"
        f"<td>{b.flip_rate:.0%}</td>"
        f"<td>{b.defect_recall if b.defect_recall is not None else '—'}</td>"
        f"<td>{b.false_block if b.false_block is not None else '—'}</td></tr>"
        for b in metrics.per_bundle
    )
    worst = "".join(
        f"<li><code>{html.escape(w['bundle_id'])}</code> — flip {w['flip_rate']:.0%}, "
        f"{w['pass_flips']} transitions</li>"
        for w in metrics.worst_offenders
    )
    recall = (
        f"{metrics.defect_recall_overall:.1%} (n={metrics.defect_recall_denominator})"
        if metrics.defect_recall_overall is not None
        else "n/a"
    )
    false_line = (
        f"{metrics.false_block_count}/{metrics.clean_bundle_count} "
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
<li>Mean same-input flip rate: <strong>{metrics.flip_rate_overall:.1%}</strong></li>
<li>Bundles with any flip: {metrics.bundles_with_any_flip}</li>
<li>Defect recall (adjudicated): <strong>{recall}</strong></li>
<li>False blocks on clean bundles: <strong>{false_line}</strong></li>
<li>Board review rounds — median {metrics.loop_median:.1f}, p90 {metrics.loop_p90:.1f}</li>
</ul>
<h2>Three worst offenders</h2>
<ul>{worst}</ul>
<h2>All bundles</h2>
<table>
<thead><tr><th>Bundle</th><th>Flip rate</th><th>Defect recall</th><th>False block</th></tr></thead>
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
            "defect_recall_overall": metrics.defect_recall_overall,
            "false_block_rate": metrics.false_block_rate,
            "loop_median": metrics.loop_median,
            "loop_p90": metrics.loop_p90,
            "worst_offenders": metrics.worst_offenders,
            "recurring_requirements": metrics.recurring_requirements,
        },
        "per_bundle": [
            {
                "bundle_id": b.bundle_id,
                "flip_rate": b.flip_rate,
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
    if judge_samples:
        payload["judge_samples"] = judge_samples
    (out_dir / "scorecard.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
