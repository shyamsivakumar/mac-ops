#!/usr/bin/env python3
"""Per model: pass rate, and turns, dollars and tokens per solved card, from a ladder run or Harbor logs. Read-only."""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRICES = json.loads((HERE.parent.parent / "coordinator" / "model_prices.json").read_text())["models"]
sys.path[:0] = [str(HERE), str(HERE.parent.parent / "coordinator" / "bin")]

import models
import score


def estimated_cost(model, agent_result):
    price = PRICES.get(model)
    tokens = [agent_result.get(k) for k in ("n_input_tokens", "n_output_tokens")]
    if price is None or None in tokens:
        return None
    return (tokens[0] * price["inputPerMTok"] + tokens[1] * price["outputPerMTok"]) / 1e6


def harbor_trials(root):
    trials, bad = [], 0
    for path in sorted(root.rglob("result.json")):
        try:
            result = json.loads(path.read_text())
        except json.JSONDecodeError:
            bad += 1
            continue
        model = ((result.get("config") or {}).get("agent") or {}).get("model_name")
        if "trial_name" not in result or not model:
            continue
        agent_result = result.get("agent_result") or {}
        requests, tokens = score.trial_usage(path, agent_result)
        reported = agent_result.get("cost_usd")
        estimate = estimated_cost(model, agent_result) if reported is None else None
        reward = ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward")
        trials.append(
            {
                "model": model,
                "task": result["task_name"],
                "correct": reward is not None and reward >= 1.0,
                "requests": requests if requests is not None else (agent_result.get("metadata") or {}).get("turns"),
                "tokens": tokens,
                "cost": reported if reported is not None else estimate,
                "estimated": estimate is not None,
            }
        )
    return trials, bad


def load(root):
    if (root / "run.json").exists():
        record = json.loads((root / "run.json").read_text())
        held = [t["id"] for t in record["tasks"] if t.get("heldout")]
        scope = "held-out cases" if held else "all cases (the run flags none held out)"
        return score.load_trials(root), held or [t["id"] for t in record["tasks"]], [m["id"] for m in record["models"]], scope, 0
    trials, bad = harbor_trials(root)
    return trials, sorted({t["task"] for t in trials}), [], "all cases (Harbor logs carry no held-out flag)", bad


def figures(trials):
    s = score.summarize(trials)
    spend = score.total(trials, "cost")
    return {
        "runs": s["runs"],
        "solved": s["correct"],
        "pass_rate": s["pass_rate"],
        "turns_per_solved": s["requests_per_correct"],
        "spend": spend,
        "cost_per_solved": score.per_correct(spend, s["correct"]),
        "estimated": any(t.get("estimated") for t in trials),
        "tokens_per_solved": s["tokens_per_correct"],
    }


def report(trials, cases, listed):
    on_cases = [t for t in trials if t["task"] in cases]
    by_model = {m: [t for t in on_cases if t["model"] == m] for m in sorted({t["model"] for t in trials} | set(listed))}
    measured = [rows for rows in by_model.values() if rows]
    shared = [c for c in cases if all(any(t["task"] == c for t in rows) for rows in measured)]
    return {m: figures([t for t in rows if t["task"] in shared]) if rows and shared else None for m, rows in by_model.items()}, shared


def money(f):
    if f["spend"] is None:
        return "n/a"
    label = "est. " if f["estimated"] else ""
    return f"{label}${f['cost_per_solved']:.4f}" if f["solved"] else "none solved"


def show(figs, shared, scope, bad):
    print(f"cases: {len(shared)} shared by every measured model ({scope})" + (f"; {bad} unreadable result files skipped" if bad else ""))
    print(f"{'model':<28}{'runs':>5}{'solved':>7}{'pass':>7}{'turns/solved':>13}{'$/solved':>18}{'tokens/solved':>15}")
    for model, f in figs.items():
        if f is None:
            print(f"{model:<28}not measured on the shared cases")
            continue
        turns = "?" if f["turns_per_solved"] is None else f"{f['turns_per_solved']:.1f}"
        tokens = "?" if f["tokens_per_solved"] is None else f"{f['tokens_per_solved']:.0f}"
        print(f"{model:<28}{f['runs']:>5}{f['solved']:>7}{f['pass_rate']:>7.0%}{turns:>13}{money(f):>18}{tokens:>15}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="a ladder run directory (with run.json) or a folder of Harbor logs")
    parser.add_argument("--list", default="build", choices=models.LISTS, help="the models.json list the pick is made from")
    args = parser.parse_args(argv)
    trials, cases, listed, scope, bad = load(args.root)
    figs, shared = report(trials, cases, listed)
    show(figs, shared, scope, bad)
    stats = {
        m: {
            "pass_rate": f["pass_rate"],
            "cost_per_solved": f["cost_per_solved"],
            "tokens_per_solved": f["tokens_per_solved"],
            "turns_per_solved": f["turns_per_solved"],
        }
        for m, f in figs.items()
        if f
    }
    entry, reason = models.measured_pick(args.list, stats)
    print(f"would pick: {entry['id'] if entry else 'nothing'} ({reason})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
