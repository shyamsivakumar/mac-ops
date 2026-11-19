#!/usr/bin/env python3
"""Score a ladder run directory into reports/<run-id>.json and .md."""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def trial_cost(agent_result, price):
    if agent_result.get("cost_usd") is not None:
        return agent_result["cost_usd"]
    tokens = [agent_result.get(k) for k in ("n_input_tokens", "n_cache_tokens", "n_output_tokens")]
    rates = [price.get(k) if price else None for k in ("input_per_mtok", "cache_read_per_mtok", "output_per_mtok")]
    if None in tokens or None in rates:
        return None
    n_in, n_cache, n_out = tokens
    r_in, r_cache, r_out = rates
    return ((n_in - n_cache) * r_in + n_cache * r_cache + n_out * r_out) / 1_000_000


def load_trials(run_dir, prices):
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
            "cost": trial_cost(agent_result, prices.get(model)),
        })
    return trials


def summarize(trials):
    runs = len(trials)
    correct = sum(t["correct"] for t in trials)
    costs = [t["cost"] for t in trials]
    verified = runs > 0 and None not in costs and sum(costs) > 0
    cost = sum(costs) if verified else None
    return {
        "runs": runs,
        "correct": correct,
        "pass_rate": correct / runs if runs else None,
        "cost_usd": cost,
        "cost_status": "OK" if verified else "UNVERIFIED",
        "cost_per_correct": cost / correct if verified and correct else None,
        "correct_per_dollar": correct / cost if verified else None,
    }


def score_model(trials, meta):
    kind = lambda t: meta.get(t["task"], {}).get("type", "untyped")
    heldout = lambda t: meta.get(t["task"], {}).get("heldout", False)
    by_task = {}
    for t in trials:
        by_task.setdefault(t["task"], []).append(t["correct"])
    return {
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
        "| Model | Runs | Pass rate | Cost USD | Cost per correct | Flaky tasks |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for model, s in report["models"].items():
        lines.append(
            f"| {model} | {s['runs']} | {fmt(s['pass_rate'], '{:.1%}')} | {fmt(s['cost_usd'], '{:.4f}')} "
            f"| {fmt(s['cost_per_correct'], '{:.4f}')} | {len(s['flaky_tasks'])} |"
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
    parser.add_argument("--prices", type=Path, default=HERE / "prices.json")
    parser.add_argument("--out-dir", type=Path, default=HERE / "reports")
    args = parser.parse_args(argv)

    record = json.loads((args.run_dir / "run.json").read_text())
    meta = {t["id"]: t for t in record["tasks"]}
    trials = load_trials(args.run_dir, json.loads(args.prices.read_text()))
    report = {
        "run_id": record["run_id"],
        "repeats": record["repeats"],
        "unreachable": record["unreachable"],
        "models": {m: score_model([t for t in trials if t["model"] == m], meta) for m in sorted({t["model"] for t in trials})},
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / f"{record['run_id']}.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.out_dir / f"{record['run_id']}.md").write_text(render_markdown(report))
    print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
