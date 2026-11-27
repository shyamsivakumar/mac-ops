#!/usr/bin/env python3
"""Per model: pass rate, and turns, dollars and tokens per solved card, from a ladder run or the lane journal. Read-only."""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent.parent / "coordinator" / "bin")]

import models
import outcomes
import score


def journal_trials(journal_dir):
    cards = {}
    for row in outcomes.read_journal(journal_dir):
        key = (row.get("repo"), row.get("ticket"))
        if None in key:
            continue
        card = cards.setdefault(key, {"starts": 0, "closed": False, "done": False})
        if row["event"] == "ticket_started":
            data = row["data"]
            card.setdefault("model", data.get("builder"))
            card.setdefault("type", data.get("taskType"))
            card["starts"] += 1
        elif row["event"] in ("ticket_closed", "ticket_abandoned"):
            card["done"] = True
            card["closed"] = row["event"] == "ticket_closed"
    return [
        {"model": c["model"], "task": f"{r}#{t}", "type": c["type"], "correct": c["closed"],
         "requests": c["starts"], "tokens": None, "cost": None}
        for (r, t), c in cards.items()
        if c["done"] and c.get("model")
    ]


def load(root, card_type):
    if (root / "run.json").exists():
        record = json.loads((root / "run.json").read_text())
        held = [t["id"] for t in record["tasks"] if t.get("heldout")]
        scope = "held-out cases" if held else "all cases (the run flags none held out)"
        return score.load_trials(root), held or [t["id"] for t in record["tasks"]], [m["id"] for m in record["models"]], scope
    trials = [t for t in journal_trials(root) if card_type in (None, t["type"])]
    return trials, None, [], f"journal cards closed or abandoned, type {card_type or 'any'}; turns are lane starts"


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
        "tokens_per_solved": s["tokens_per_correct"],
    }


def report(trials, cases, listed):
    by_model = {m: [t for t in trials if t["model"] == m and (cases is None or t["task"] in cases)] for m in sorted({t["model"] for t in trials} | set(listed))}
    if cases is None:
        return {m: figures(rows) if rows else None for m, rows in by_model.items()}, None
    measured = [rows for rows in by_model.values() if rows]
    shared = [c for c in cases if all(any(t["task"] == c for t in rows) for rows in measured)]
    return {m: figures([t for t in rows if t["task"] in shared]) if rows and shared else None for m, rows in by_model.items()}, shared


def money(f):
    if f["spend"] is None:
        return "n/a"
    return f"${f['cost_per_solved']:.4f}" if f["solved"] else "none solved"


def show(figs, shared, scope):
    print(f"cases: {'every resolved card' if shared is None else f'{len(shared)} shared by every measured model'} ({scope})")
    print(f"{'model':<28}{'runs':>5}{'solved':>7}{'pass':>7}{'turns/solved':>13}{'$/solved':>13}{'tokens/solved':>15}")
    for model, f in figs.items():
        if f is None:
            print(f"{model:<28}not measured on the shared cases")
            continue
        turns = "?" if f["turns_per_solved"] is None else f"{f['turns_per_solved']:.1f}"
        tokens = "?" if f["tokens_per_solved"] is None else f"{f['tokens_per_solved']:.0f}"
        print(f"{model:<28}{f['runs']:>5}{f['solved']:>7}{f['pass_rate']:>7.0%}{turns:>13}{money(f):>13}{tokens:>15}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="a ladder run directory (with run.json) or the lane journal directory")
    parser.add_argument("--type", help="journal source only: keep cards of this taskType")
    parser.add_argument("--list", default="build", choices=models.LISTS, help="the models.json list the pick is made from")
    args = parser.parse_args(argv)
    trials, cases, listed, scope = load(args.root, args.type)
    figs, shared = report(trials, cases, listed)
    show(figs, shared, scope)
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
