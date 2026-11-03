"""Daily objective eval over stored session traces."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .store import day_key, evals_dir, load_day_traces, state_root


def _has_merged_pr(trace: dict[str, Any]) -> bool:
    for pr in trace.get("pull_requests") or []:
        state = (pr.get("state") or "").lower()
        if state == "merged" or pr.get("merged_at"):
            return True
    return False


def _ci_green(trace: dict[str, Any]) -> bool:
    prs = trace.get("pull_requests") or []
    if not prs:
        return False
    return all(
        (pr.get("checks_state") or "").lower() in {"passing", "success", "neutral", ""}
        for pr in prs
    ) and any(
        (pr.get("checks_state") or "").lower() in {"passing", "success"} for pr in prs
    )


def _review_clean(trace: dict[str, Any]) -> bool:
    """Objective check: no CHANGES_REQUESTED; treat missing decision as unknown-pass for merge proof."""
    prs = trace.get("pull_requests") or []
    if not prs:
        return False
    for pr in prs:
        decision = (pr.get("review_decision") or "").upper()
        if decision == "CHANGES_REQUESTED" and not _has_merged_pr(trace):
            return False
    # Snapshot does not carry critical/major counts; 0 critical/major is inferred
    # when merged with passing checks and no CHANGES_REQUESTED.
    if _has_merged_pr(trace) and _ci_green(trace):
        return all(
            (pr.get("review_decision") or "").upper() != "CHANGES_REQUESTED"
            for pr in prs
        )
    return False


def _ci_red(trace: dict[str, Any]) -> bool:
    for pr in trace.get("pull_requests") or []:
        state = (pr.get("checks_state") or "").lower()
        if state in {"failing", "failure", "failed", "error"}:
            return True
    return False


def _review_blocked(trace: dict[str, Any]) -> bool:
    for pr in trace.get("pull_requests") or []:
        if (pr.get("review_decision") or "").upper() == "CHANGES_REQUESTED":
            return True
    return False


def score_trace(trace: dict[str, Any]) -> dict[str, Any]:
    merged = _has_merged_pr(trace)
    blocker = bool(trace.get("named_blocker"))
    ended_ok = merged or blocker
    # Proof = merged with green CI and no CHANGES_REQUESTED (critical/major proxy).
    proof = merged and _ci_green(trace) and _review_clean(trace)
    # "Claimed done without proof": completed run still open, CI red or review blocked.
    status = (trace.get("status") or "").lower()
    claimed_without_proof = (
        status == "completed"
        and bool(trace.get("pull_requests"))
        and not merged
        and (_ci_red(trace) or _review_blocked(trace))
    )
    stopped_green = (
        status in {"interrupted", "cancelled"} and _ci_green(trace) and not merged
    )
    outside = list(trace.get("files_outside_worktree") or [])
    preview = list(trace.get("preview_or_playwright") or [])
    # Flags are actionable misses only; merge/blocker rate stays a summary metric.
    flags = []
    if claimed_without_proof:
        flags.append("claimed_done_without_proof")
    if stopped_green:
        flags.append("stopped_while_green")
    if outside:
        flags.append("files_outside_worktree")
    if preview:
        flags.append("preview_or_playwright")

    return {
        "run_id": trace.get("run_id"),
        "thread_id": trace.get("thread_id"),
        "task_key": trace.get("task_key"),
        "title": trace.get("title"),
        "provider": trace.get("provider"),
        "model": trace.get("model"),
        "status": trace.get("status"),
        "duration_ms": trace.get("duration_ms"),
        "cost_usd": trace.get("cost_usd"),
        "merged_pr": merged,
        "named_blocker": blocker,
        "ended_with_merge_or_blocker": ended_ok,
        "claimed_done_with_proof": proof,
        "claimed_done_without_proof": claimed_without_proof,
        "stopped_before_merge_while_green": stopped_green,
        "files_outside_worktree_count": len(outside),
        "preview_or_playwright_count": len(preview),
        "pull_requests": trace.get("pull_requests") or [],
        "flags": flags,
    }


def evaluate_day(day: str | None = None, *, root: Path | None = None) -> dict[str, Any]:
    day = day or day_key()
    traces = load_day_traces(day, root=root)
    rows = [score_trace(t) for t in traces]
    by_provider: dict[str, int] = defaultdict(int)
    by_status: dict[str, int] = defaultdict(int)
    flag_counts: dict[str, int] = defaultdict(int)
    merged_rows = [r for r in rows if r["merged_pr"]]
    durations = [
        r["duration_ms"] for r in merged_rows if isinstance(r.get("duration_ms"), int)
    ]
    costs = [
        r["cost_usd"]
        for r in merged_rows
        if isinstance(r.get("cost_usd"), (int, float))
    ]

    for r in rows:
        by_provider[str(r.get("provider") or "unknown")] += 1
        by_status[str(r.get("status") or "unknown")] += 1
        for f in r["flags"]:
            flag_counts[f] += 1

    summary = {
        "day": day,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "run_count": len(rows),
        "by_provider": dict(sorted(by_provider.items())),
        "by_status": dict(sorted(by_status.items())),
        "merged_pr_count": len(merged_rows),
        "named_blocker_count": sum(1 for r in rows if r["named_blocker"]),
        "ended_with_merge_or_blocker": sum(
            1 for r in rows if r["ended_with_merge_or_blocker"]
        ),
        "claimed_done_with_proof": sum(1 for r in rows if r["claimed_done_with_proof"]),
        "claimed_done_without_proof": sum(
            1 for r in rows if r.get("claimed_done_without_proof")
        ),
        "stopped_before_merge_while_green": sum(
            1 for r in rows if r["stopped_before_merge_while_green"]
        ),
        "files_outside_worktree": sum(
            1 for r in rows if r["files_outside_worktree_count"]
        ),
        "preview_or_playwright": sum(
            1 for r in rows if r["preview_or_playwright_count"]
        ),
        "flag_counts": dict(sorted(flag_counts.items())),
        "time_per_merged_pr_ms": {
            "count": len(durations),
            "total": sum(durations) if durations else 0,
            "mean": (sum(durations) / len(durations)) if durations else None,
        },
        "cost_per_merged_pr_usd": {
            "count": len(costs),
            "total": sum(costs) if costs else 0,
            "mean": (sum(costs) / len(costs)) if costs else None,
        },
        "regressions": [r for r in rows if r["flags"]],
        "rows": rows,
    }
    return summary


def _fmt_ms(ms: float | None) -> str:
    if ms is None:
        return "-"
    s = float(ms) / 1000.0
    if s < 60:
        return f"{s:.0f}s"
    m, s = divmod(round(s), 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def render_markdown(
    summary: dict[str, Any], *, baseline: dict[str, Any] | None = None
) -> str:
    day = summary["day"]
    lines = [
        f"# Agent session eval — {day}",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Runs: **{summary['run_count']}**",
        f"- Providers: {', '.join(f'{k}={v}' for k, v in summary['by_provider'].items()) or 'none'}",
        f"- Statuses: {', '.join(f'{k}={v}' for k, v in summary['by_status'].items()) or 'none'}",
        f"- Merged PR runs: **{summary['merged_pr_count']}**",
        f"- Named blocker runs: **{summary['named_blocker_count']}**",
        f"- Ended with merge or blocker: **{summary['ended_with_merge_or_blocker']}**",
        f"- Claimed done with proof (merged + CI green, no CHANGES_REQUESTED): **{summary['claimed_done_with_proof']}**",
        f"- Claimed done without proof (open PR, CI red or CHANGES_REQUESTED): **{summary.get('claimed_done_without_proof', 0)}**",
        f"- Stopped before merge while green: **{summary['stopped_before_merge_while_green']}**",
        f"- Touched files outside worktree: **{summary['files_outside_worktree']}**",
        f"- Preview / Playwright / panel tools: **{summary['preview_or_playwright']}**",
        f"- Time per merged PR (mean): **{_fmt_ms((summary['time_per_merged_pr_ms'] or {}).get('mean'))}** "
        f"(n={summary['time_per_merged_pr_ms']['count']})",
        f"- Cost per merged PR (mean USD): **{summary['cost_per_merged_pr_usd']['mean']}** "
        f"(n={summary['cost_per_merged_pr_usd']['count']}; tokens/cost often absent in T3 projections)",
        "",
    ]
    if baseline:
        lines.extend(["## Regressions vs prior day", ""])
        for key in (
            "stopped_before_merge_while_green",
            "files_outside_worktree",
            "preview_or_playwright",
            "claimed_done_with_proof",
        ):
            before = baseline.get(key, 0)
            after = summary.get(key, 0)
            # Higher is worse for the first three; lower proof is worse.
            worse = (
                after > before if key != "claimed_done_with_proof" else after < before
            )
            mark = " **REGRESSION**" if worse else ""
            lines.append(f"- {key}: {before} → {after}{mark}")
        lines.append("")

    lines.extend(
        [
            "## Daily table",
            "",
            "| Task | Provider | Model | Status | Dur | Merged | Flags |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for r in summary["rows"]:
        flags = ",".join(r["flags"]) if r["flags"] else ""
        lines.append(
            "| {task} | {prov} | {model} | {status} | {dur} | {merged} | {flags} |".format(
                task=(r.get("task_key") or r.get("title") or "")[:40].replace("|", "/"),
                prov=r.get("provider") or "",
                model=(r.get("model") or "")[:24],
                status=r.get("status") or "",
                dur=_fmt_ms(r.get("duration_ms")),
                merged="yes" if r.get("merged_pr") else "",
                flags=flags.replace("|", "/"),
            )
        )
    if not summary["rows"]:
        lines.append("| (none) | | | | | | |")
    lines.extend(["", "## Flagged runs", ""])
    regs = summary.get("regressions") or []
    if not regs:
        lines.append("None.")
    else:
        for r in regs[:50]:
            lines.append(
                f"- `{r.get('task_key') or r.get('title')}` ({r.get('provider')}/{r.get('model')}): "
                f"{', '.join(r['flags'])}"
            )
    lines.append("")
    return "\n".join(lines)


def write_day_report(
    day: str | None = None,
    *,
    root: Path | None = None,
    baseline_day: str | None = None,
) -> dict[str, Any]:
    day = day or day_key()
    summary = evaluate_day(day, root=root)
    baseline = None
    if baseline_day:
        base_path = evals_dir(root) / f"{baseline_day}.json"
        if base_path.is_file():
            baseline = json.loads(base_path.read_text(encoding="utf-8"))
    md = render_markdown(summary, baseline=baseline)
    out = evals_dir(root)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / f"{day}.json"
    md_path = out / f"{day}.md"
    # Drop bulky rows duplicate in markdown-only consumers; keep in JSON.
    json_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    md_path.write_text(md, encoding="utf-8")
    return {
        "day": day,
        "json": str(json_path),
        "md": str(md_path),
        "run_count": summary["run_count"],
        "flag_counts": summary["flag_counts"],
        "state_root": str(state_root(root)),
    }
