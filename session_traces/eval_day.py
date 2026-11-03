"""Daily objective eval over stored session traces."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .store import day_key, evals_dir, load_day_traces, state_root


def _pr_key(pr: dict[str, Any]) -> str | None:
    repo = pr.get("repository")
    number = pr.get("number")
    if repo is not None and number is not None:
        return f"{repo}#{number}"
    url = pr.get("url")
    return str(url) if url else None


def _timed_prs(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """PRs whose merge timing relative to this run is known (not post-run)."""
    if (trace.get("outcome_evidence") or "known") == "unknown":
        return []
    out = []
    for pr in trace.get("pull_requests") or []:
        if not isinstance(pr, dict):
            continue
        timing = pr.get("timing") or "known"
        if timing in {"unknown", "post_run_merge"}:
            continue
        out.append(pr)
    return out


def _pr_merged(pr: dict[str, Any]) -> bool:
    if pr.get("merge_by_end") is True:
        return True
    state = (pr.get("state") or "").lower()
    return state == "merged" or bool(pr.get("merged_at"))


def _pr_ci_green(pr: dict[str, Any]) -> bool:
    state = (pr.get("checks_state") or "").lower()
    return state in {"passing", "success"}


def _pr_ci_red(pr: dict[str, Any]) -> bool:
    state = (pr.get("checks_state") or "").lower()
    return state in {"failing", "failure", "failed", "error"}


def _pr_review_blocked(pr: dict[str, Any]) -> bool:
    return (pr.get("review_decision") or "").upper() == "CHANGES_REQUESTED"


def _has_merged_pr(trace: dict[str, Any]) -> bool:
    return any(_pr_merged(pr) for pr in _timed_prs(trace))


def _proven_same_pr(trace: dict[str, Any]) -> bool:
    """Merge + green CI + acceptable review must hold on one PR.

    CI/review fields are only present when historical snapshot timing is known
    at or before run end; otherwise proof stays missing (not disproven).
    """
    for pr in _timed_prs(trace):
        if not _pr_merged(pr):
            continue
        if pr.get("checks_state") is None:
            continue
        if not _pr_ci_green(pr):
            continue
        if _pr_review_blocked(pr):
            continue
        return True
    return False


def _disproven_same_pr(trace: dict[str, Any]) -> bool:
    for pr in _timed_prs(trace):
        if pr.get("checks_state") is None and pr.get("review_decision") is None:
            continue
        if _pr_ci_red(pr) or _pr_review_blocked(pr):
            return True
    return False


def _ci_green_known(trace: dict[str, Any]) -> bool:
    """True only when some timed PR has known-by-end passing checks."""
    return any(
        pr.get("checks_state") is not None and _pr_ci_green(pr)
        for pr in _timed_prs(trace)
    )


def proof_status(trace: dict[str, Any]) -> str:
    """proven | disproven | missing | n/a for objective done-with-proof scoring."""
    status = (trace.get("status") or "").lower()
    if status != "completed":
        return "n/a"
    if trace.get("named_blocker"):
        return "proven"  # named blocker is an accepted terminal outcome
    if (trace.get("outcome_evidence") or "known") == "unknown":
        return "missing"
    if _disproven_same_pr(trace):
        return "disproven"
    if _proven_same_pr(trace):
        return "proven"
    return "missing"


def score_trace(trace: dict[str, Any]) -> dict[str, Any]:
    merged = _has_merged_pr(trace)
    blocker = bool(trace.get("named_blocker"))
    ended_ok = merged or blocker
    status = (trace.get("status") or "").lower()
    pstatus = proof_status(trace)
    proof = pstatus == "proven" and _proven_same_pr(trace)
    # Named blocker counts as ended_ok but not "claimed done with CI proof".
    if pstatus == "proven" and blocker and not merged:
        proof = False
    claimed_without_proof = pstatus == "disproven"
    missing_proof = pstatus == "missing"
    stopped_green = (
        status in {"interrupted", "cancelled"} and _ci_green_known(trace) and not merged
    )
    outside = list(trace.get("files_outside_worktree") or [])
    preview = list(trace.get("preview_or_playwright") or [])
    flags = []
    if claimed_without_proof:
        flags.append("claimed_done_without_proof")
    if missing_proof:
        flags.append("missing_proof")
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
        "proof_status": pstatus,
        "claimed_done_with_proof": proof,
        "claimed_done_without_proof": claimed_without_proof,
        "missing_proof": missing_proof,
        "stopped_before_merge_while_green": stopped_green,
        "files_outside_worktree_count": len(outside),
        "preview_or_playwright_count": len(preview),
        "pull_requests": trace.get("pull_requests") or [],
        "outcome_evidence": trace.get("outcome_evidence") or "known",
        "flags": flags,
    }


def _merged_pr_metrics(
    day_rows: list[dict[str, Any]],
    *,
    contribution_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Group by canonical PR; sum contributing runs across days for today's merges."""
    merged_keys: set[str] = set()
    for r in day_rows:
        if not r.get("merged_pr"):
            continue
        for pr in r.get("pull_requests") or []:
            timing = pr.get("timing") or "known"
            if timing in {"unknown", "post_run_merge"}:
                continue
            if not _pr_merged(pr):
                continue
            key = _pr_key(pr)
            if key:
                merged_keys.add(key)

    by_pr: dict[str, dict[str, Any]] = {
        key: {"duration_ms": 0, "cost_usd": 0.0, "cost_n": 0, "runs": 0}
        for key in merged_keys
    }
    # Include earlier-day runs that linked the same PR (without changing their
    # own day's merged_pr attribution).
    pool = contribution_rows if contribution_rows is not None else day_rows
    for r in pool:
        seen_keys: set[str] = set()
        for pr in r.get("pull_requests") or []:
            key = _pr_key(pr)
            if not key or key not in merged_keys or key in seen_keys:
                continue
            seen_keys.add(key)
            bucket = by_pr[key]
            bucket["runs"] += 1
            if isinstance(r.get("duration_ms"), int):
                bucket["duration_ms"] += r["duration_ms"]
            if isinstance(r.get("cost_usd"), (int, float)):
                bucket["cost_usd"] += float(r["cost_usd"])
                bucket["cost_n"] += 1
    durations = [b["duration_ms"] for b in by_pr.values()]
    costs = [b["cost_usd"] for b in by_pr.values() if b["cost_n"]]
    return {
        "distinct_merged_prs": len(by_pr),
        "time_per_merged_pr_ms": {
            "count": len(durations),
            "total": sum(durations) if durations else 0,
            "mean": (sum(durations) / len(durations)) if durations else None,
            "note": "sum of contributing run durations per distinct PR across stored days",
        },
        "cost_per_merged_pr_usd": {
            "count": len(costs),
            "total": sum(costs) if costs else 0,
            "mean": (sum(costs) / len(costs)) if costs else None,
            "note": "sum of contributing run costs per distinct PR across stored days",
        },
        "prs": sorted(by_pr.keys()),
    }


def _all_scored_rows(root: Path | None) -> list[dict[str, Any]]:
    from .store import traces_dir

    base = traces_dir(root)
    if not base.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(base.iterdir()):
        if not path.is_dir():
            continue
        name = path.name
        if len(name) != 10 or name[4] != "-" or name[7] != "-":
            continue
        for trace in load_day_traces(name, root=root):
            rows.append(score_trace(trace))
    return rows


def evaluate_day(day: str | None = None, *, root: Path | None = None) -> dict[str, Any]:
    day = day or day_key()
    traces = load_day_traces(day, root=root)
    rows = [score_trace(t) for t in traces]
    by_provider: dict[str, int] = defaultdict(int)
    by_status: dict[str, int] = defaultdict(int)
    flag_counts: dict[str, int] = defaultdict(int)
    pr_metrics = _merged_pr_metrics(rows, contribution_rows=_all_scored_rows(root))

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
        "merged_pr_count": pr_metrics["distinct_merged_prs"],
        "merged_pr_run_count": sum(1 for r in rows if r["merged_pr"]),
        "named_blocker_count": sum(1 for r in rows if r["named_blocker"]),
        "ended_with_merge_or_blocker": sum(
            1 for r in rows if r["ended_with_merge_or_blocker"]
        ),
        "claimed_done_with_proof": sum(1 for r in rows if r["claimed_done_with_proof"]),
        "claimed_done_without_proof": sum(
            1 for r in rows if r.get("claimed_done_without_proof")
        ),
        "missing_proof": sum(1 for r in rows if r.get("missing_proof")),
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
        "time_per_merged_pr_ms": pr_metrics["time_per_merged_pr_ms"],
        "cost_per_merged_pr_usd": pr_metrics["cost_per_merged_pr_usd"],
        "distinct_merged_prs": pr_metrics["prs"],
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
        f"- Distinct merged PRs: **{summary['merged_pr_count']}** "
        f"(across {summary.get('merged_pr_run_count', 0)} runs)",
        f"- Named blocker runs: **{summary['named_blocker_count']}**",
        f"- Ended with merge or blocker: **{summary['ended_with_merge_or_blocker']}**",
        f"- Claimed done with proof: **{summary['claimed_done_with_proof']}**",
        f"- Claimed done without proof (CI red / CHANGES_REQUESTED): "
        f"**{summary.get('claimed_done_without_proof', 0)}**",
        f"- Missing proof (completed, no proven merge/blocker): "
        f"**{summary.get('missing_proof', 0)}**",
        f"- Stopped before merge while green: **{summary['stopped_before_merge_while_green']}**",
        f"- Touched files outside worktree: **{summary['files_outside_worktree']}**",
        f"- Preview / Playwright / panel tools: **{summary['preview_or_playwright']}**",
        f"- Time per distinct merged PR (mean of summed run durations): "
        f"**{_fmt_ms((summary['time_per_merged_pr_ms'] or {}).get('mean'))}** "
        f"(n={summary['time_per_merged_pr_ms']['count']})",
        f"- Cost per distinct merged PR (mean USD): "
        f"**{summary['cost_per_merged_pr_usd']['mean']}** "
        f"(n={summary['cost_per_merged_pr_usd']['count']}; often absent in T3 projections)",
        "",
    ]
    if baseline:
        lines.extend(["## Regressions vs prior day", ""])
        for key in (
            "stopped_before_merge_while_green",
            "files_outside_worktree",
            "preview_or_playwright",
            "missing_proof",
            "claimed_done_with_proof",
        ):
            before = baseline.get(key, 0)
            after = summary.get(key, 0)
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
            "| Task | Provider | Model | Status | Dur | Proof | Flags |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for r in summary["rows"]:
        flags = ",".join(r["flags"]) if r["flags"] else ""
        lines.append(
            "| {task} | {prov} | {model} | {status} | {dur} | {proof} | {flags} |".format(
                task=(r.get("task_key") or r.get("title") or "")[:40].replace("|", "/"),
                prov=r.get("provider") or "",
                model=(r.get("model") or "")[:24],
                status=r.get("status") or "",
                dur=_fmt_ms(r.get("duration_ms")),
                proof=r.get("proof_status") or "",
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
