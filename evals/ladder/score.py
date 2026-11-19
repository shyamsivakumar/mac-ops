#!/usr/bin/env python3
"""Score a ladder run directory into reports/<run-id>.json and .md."""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def trial_usage(path, agent_result):
    tokens = [agent_result.get(k) for k in ("n_input_tokens", "n_output_tokens")]
    trajectory = path.parent / "agent" / "trajectory.json"
    requests = None
    if trajectory.exists():
        requests = sum(1 for step in json.loads(trajectory.read_text())["steps"] if step.get("source") == "agent")
    return requests, None if None in tokens else sum(tokens)


def load_trials(run_dir):
    trials = []
    for path in sorted(run_dir.glob("*/*/*/*/result.json")):
        model, task = path.relative_to(run_dir).parts[:2]
        result = json.loads(path.read_text())
        reward = ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward")
        agent_result = result.get("agent_result") or {}
        requests, tokens = trial_usage(path, agent_result)
        trials.append({
            "model": model,
            "task": task,
            "correct": reward is not None and reward >= 1.0,
            "requests": requests,
            "tokens": tokens,
            "cost": agent_result.get("cost_usd"),
        })
    return trials


def missing_trials(run_dir, record):
    """Name every scheduled trial with no result, so a short run cannot be scored."""
    short = []
    for model in record["models"]:
        for task in record["tasks"]:
            found = len(list((run_dir / model["id"] / task["id"]).glob("*/*/result.json")))
            if found != record["repeats"]:
                short.append(f"{model['id']}/{task['id']}: {found} of {record['repeats']} trials")
    return short


def total(trials, key):
    values = [t[key] for t in trials]
    return sum(values) if values and None not in values else None


def per_correct(used, correct):
    return used / correct if used is not None and correct else None


def summarize(trials, unit="requests"):
    runs = len(trials)
    correct = sum(t["correct"] for t in trials)
    requests, tokens = total(trials, "requests"), total(trials, "tokens")
    quota = requests if unit == "requests" else tokens
    return {
        "runs": runs,
        "correct": correct,
        "pass_rate": correct / runs if runs else None,
        "requests_per_correct": per_correct(requests, correct),
        "tokens_per_correct": per_correct(tokens, correct),
        "quota_status": "OK" if quota is not None else "UNVERIFIED",
        "quota_per_correct": per_correct(quota, correct),
        "cost_usd_informational": total(trials, "cost"),
    }


def by_task_rows(trials):
    rows = {}
    for t in trials:
        rows.setdefault(t["task"], []).append(t)
    return rows


def score_model(trials, meta, unit, confirmed):
    kind = lambda t: meta.get(t["task"], {}).get("type", "untyped")
    heldout = lambda t: meta.get(t["task"], {}).get("heldout", False)
    by_task = {task: [t["correct"] for t in rows] for task, rows in by_task_rows(trials).items()}
    return {
        "quota_unit": unit,
        "quota_unit_confirmed": confirmed,
        **summarize(trials, unit),
        "train": summarize([t for t in trials if not heldout(t)], unit),
        "heldout": summarize([t for t in trials if heldout(t)], unit),
        "by_type": {k: summarize([t for t in trials if kind(t) == k], unit) for k in sorted({kind(t) for t in trials})},
        "per_task": {
            task: {"runs": len(rows), "correct": sum(t["correct"] for t in rows)}
            for task, rows in sorted(by_task_rows(trials).items())
        },
        "flaky_tasks": [
            {"task": task, "correct": sum(r), "runs": len(r)}
            for task, r in sorted(by_task.items())
            if 0 < sum(r) < len(r)
        ],
    }


def render_markdown(report):
    fmt = lambda v, p="{:.3f}": "UNVERIFIED" if v is None else p.format(v)
    lines = [
        f"# Ladder report {report['run_id']}",
        "",
        "| Model | Runs | Pass rate | Turns per correct | Tokens per correct | Quota unit | Flaky tasks |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for model, s in report["models"].items():
        lines.append(
            f"| {model} | {s['runs']} | {fmt(s['pass_rate'], '{:.1%}')} | {fmt(s['requests_per_correct'], '{:.1f}')} "
            f"| {fmt(s['tokens_per_correct'], '{:.0f}')} | {s['quota_unit']} | {len(s['flaky_tasks'])} |"
        )
    for model, s in report["models"].items():
        lines += ["", f"## {model}", "", "| Task type | Runs | Pass rate |", "| --- | --- | --- |"]
        lines += [f"| {k} | {v['runs']} | {fmt(v['pass_rate'], '{:.1%}')} |" for k, v in s["by_type"].items()]
        for f in s["flaky_tasks"]:
            lines.append(f"\nFlaky: {f['task']} ({f['correct']} of {f['runs']} correct)")
    if report["unreachable"]:
        lines += ["", "Unreachable: " + ", ".join(f"{u['id']} ({u['reason']})" for u in report["unreachable"])]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--out-dir", type=Path, default=HERE / "reports")
    args = parser.parse_args(argv)

    record = json.loads((args.run_dir / "run.json").read_text())
    short = missing_trials(args.run_dir, record)
    if short:
        sys.exit("score: the run does not match its schedule; do not score it: " + "; ".join(short))
    meta = {t["id"]: t for t in record["tasks"]}
    units = {m["id"]: m.get("quota_unit", "requests") for m in record["models"]}
    confirmed = {m["id"]: m.get("quota_unit_confirmed", False) for m in record["models"]}
    trials = load_trials(args.run_dir)
    report = {
        "run_id": record["run_id"],
        "repeats": record["repeats"],
        "unreachable": record["unreachable"],
        "tasks": record["tasks"],
        "models": {m: score_model([t for t in trials if t["model"] == m], meta, units[m], confirmed[m]) for m in sorted({t["model"] for t in trials})},
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / f"{record['run_id']}.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.out_dir / f"{record['run_id']}.md").write_text(render_markdown(report))
    print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
