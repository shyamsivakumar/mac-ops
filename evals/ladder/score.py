#!/usr/bin/env python3
"""Score a ladder run directory into reports/<run-id>.json and .md."""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def trial_quota(path, agent_result, unit):
    if unit == "tokens":
        used = [agent_result.get(k) for k in ("n_input_tokens", "n_output_tokens")]
        return None if None in used else sum(used)
    trajectory = path.parent / "agent" / "trajectory.json"
    if not trajectory.exists():
        return None
    return sum(1 for step in json.loads(trajectory.read_text())["steps"] if step.get("source") == "agent")


def load_trials(run_dir, units):
    trials = []
    for path in sorted(run_dir.glob("*/*/*/*/result.json")):
        model, task = path.relative_to(run_dir).parts[:2]
        result = json.loads(path.read_text())
        reward = ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward")
        agent_result = result.get("agent_result") or {}
        trials.append({
            "model": model,
            "task": task,
            "correct": reward is not None and reward >= 1.0,
            "quota": trial_quota(path, agent_result, units[model]),
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


def summarize(trials):
    runs = len(trials)
    correct = sum(t["correct"] for t in trials)
    quotas = [t["quota"] for t in trials]
    measured = runs > 0 and None not in quotas
    quota = sum(quotas) if measured else None
    costs = [t["cost"] for t in trials]
    return {
        "runs": runs,
        "correct": correct,
        "pass_rate": correct / runs if runs else None,
        "quota_used": quota,
        "quota_status": "OK" if measured else "UNVERIFIED",
        "quota_per_correct": quota / correct if measured and correct else None,
        "cost_usd_informational": sum(costs) if runs and None not in costs else None,
    }


def score_model(trials, meta, unit):
    kind = lambda t: meta.get(t["task"], {}).get("type", "untyped")
    heldout = lambda t: meta.get(t["task"], {}).get("heldout", False)
    by_task = {}
    for t in trials:
        by_task.setdefault(t["task"], []).append(t["correct"])
    return {
        "quota_unit": unit,
        **summarize(trials),
        "train": summarize([t for t in trials if not heldout(t)]),
        "heldout": summarize([t for t in trials if heldout(t)]),
        "by_type": {k: summarize([t for t in trials if kind(t) == k]) for k in sorted({kind(t) for t in trials})},
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
        "| Model | Runs | Pass rate | Quota unit | Quota per correct | Flaky tasks |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for model, s in report["models"].items():
        lines.append(
            f"| {model} | {s['runs']} | {fmt(s['pass_rate'], '{:.1%}')} | {s['quota_unit']} "
            f"| {fmt(s['quota_per_correct'], '{:.1f}')} | {len(s['flaky_tasks'])} |"
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
    trials = load_trials(args.run_dir, units)
    report = {
        "run_id": record["run_id"],
        "repeats": record["repeats"],
        "unreachable": record["unreachable"],
        "tasks": record["tasks"],
        "models": {m: score_model([t for t in trials if t["model"] == m], meta, units[m]) for m in sorted({t["model"] for t in trials})},
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / f"{record['run_id']}.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.out_dir / f"{record['run_id']}.md").write_text(render_markdown(report))
    print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
