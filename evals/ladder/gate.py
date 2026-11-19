#!/usr/bin/env python3
"""Decide whether candidates move up the build list; propose, never apply.

The baseline and the candidates come from one run, so one report holds both.
"""

import argparse
import datetime
import difflib
import json
import random
import sys
from pathlib import Path

import score

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def clusters(tasks):
    grouped = {}
    for t in tasks:
        grouped.setdefault(f"group:{t['group']}" if t.get("group") else f"task:{t['id']}", []).append(t["id"])
    return grouped


def pass_rate(per_task, ids):
    runs = sum(per_task[i]["runs"] for i in ids)
    return sum(per_task[i]["correct"] for i in ids) / runs


def interval(diffs, cfg):
    rng = random.Random(cfg["seed"])
    means = sorted(sum(rng.choices(diffs, k=len(diffs))) / len(diffs) for _ in range(cfg["draws"]))
    tail = (1 - cfg["confidence"]) / 2
    return means[int(cfg["draws"] * tail)], means[int(cfg["draws"] * (1 - tail)) - 1]


def decide(candidate, baseline, lo, hi, cfg):
    if lo > 0:
        return True, f"pass rate is higher, 90% interval lower bound {lo:+.3f} is above zero"
    if lo < -cfg["tie_band"] or hi > cfg["tie_band"]:
        return False, f"interval [{lo:+.3f}, {hi:+.3f}] is not inside the tie band of {cfg['tie_band']}, so there is no clear gain"
    if candidate["quota_unit"] != baseline["quota_unit"]:
        return False, f"quota not compared, units differ ({candidate['quota_unit']} vs {baseline['quota_unit']})"
    if not (candidate["quota_unit_confirmed"] and baseline["quota_unit_confirmed"]):
        return False, "no difference in pass rate, and quota is not used because a quota unit is unconfirmed"
    cand_q, base_q = candidate["quota_per_correct"], baseline["quota_per_correct"]
    if cand_q is None or not base_q:
        return False, "no difference in pass rate, and quota is not comparable: a quota per correct answer is UNVERIFIED, zero or has no correct answers"
    ratio = cand_q / base_q
    if ratio > cfg["max_quota_ratio"]:
        return False, f"no difference in pass rate, quota per correct answer is {ratio:.2f}x the baseline, need at most {cfg['max_quota_ratio']}x"
    return True, f"no difference in pass rate, wins on quota at {ratio:.2f}x the baseline per correct answer ({candidate['quota_unit']})"


def compare(report, baseline_id, cfg):
    baseline = report["models"].get(baseline_id)
    if baseline is None:
        sys.exit(f"gate: run {report['run_id']} has no entry for baseline {baseline_id}; run the baseline with the candidates")
    groups = clusters(report["tasks"])
    verdicts = {}
    for model, entry in sorted(report["models"].items()):
        if model == baseline_id:
            continue
        diffs = [pass_rate(entry["per_task"], ids) - pass_rate(baseline["per_task"], ids) for ids in groups.values()]
        lo, hi = interval(diffs, cfg)
        ok, why = decide(entry, baseline, lo, hi, cfg)
        verdicts[model] = {
            "pass_rate": entry["pass_rate"],
            "baseline_pass_rate": baseline["pass_rate"],
            "difference": sum(diffs) / len(diffs),
            "interval_90": [lo, hi],
            "interval_half_width": (hi - lo) / 2,
            "clusters": len(groups),
            "promote": ok,
            "reason": why,
            "requests_per_correct": [entry["requests_per_correct"], baseline["requests_per_correct"]],
            "tokens_per_correct": [entry["tokens_per_correct"], baseline["tokens_per_correct"]],
            "cost_usd_informational": [entry["cost_usd_informational"], baseline["cost_usd_informational"]],
        }
    return verdicts


def self_check(run_dir, model, cfg):
    record = json.loads((run_dir / "run.json").read_text())
    trials = [t for t in score.load_trials(run_dir) if t["model"] == model]
    rows_by_task = {t["id"]: [x["correct"] for x in trials if x["task"] == t["id"]] for t in record["tasks"]}
    incomplete = sorted(task for task, rows in rows_by_task.items() if len(rows) != record["repeats"])
    if incomplete or record["repeats"] // 2 < 2:
        why = f"{', '.join(incomplete)} lack scheduled trials" if incomplete else f"{record['repeats']} repeats leave fewer than 2 per half"
        return {"model": model, "not_enough_data": why, "no_difference": False}
    halves = {}
    for task, rows in rows_by_task.items():
        halves[task] = [{"runs": len(rows[k::2]), "correct": sum(rows[k::2])} for k in (0, 1)]
    diffs = [
        pass_rate({i: halves[i][0] for i in ids}, ids) - pass_rate({i: halves[i][1] for i in ids}, ids)
        for ids in clusters(record["tasks"]).values()
    ]
    lo, hi = interval(diffs, cfg)
    return {"model": model, "interval_90": [lo, hi], "no_difference": lo <= 0 <= hi}


def propose(models_text, promoted, baseline_id):
    data = json.loads(models_text)
    build = data["build"]
    moving = [e for e in build if e["id"] in promoted]
    rest = [e for e in build if e["id"] not in promoted]
    at = next(i for i, e in enumerate(rest) if e["id"] == baseline_id)
    data["build"] = rest[:at] + moving + rest[at:]
    return json.dumps(data, indent=2) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="?", type=Path, help="the score report of one run holding the baseline and the candidates")
    parser.add_argument("--self-check", nargs=2, metavar=("RUN_ID", "MODEL"), help="split a model's repeats in two and require no difference")
    parser.add_argument("--runs-dir", type=Path, default=HERE / "runs")
    parser.add_argument("--baseline", type=Path, default=HERE / "baseline.json")
    parser.add_argument("--gate", type=Path, default=HERE / "gate.json")
    parser.add_argument("--models-file", type=Path, default=ROOT / "coordinator" / "models.json")
    parser.add_argument("--out-dir", type=Path, default=HERE)
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    args = parser.parse_args(argv)

    cfg = json.loads(args.gate.read_text())
    if args.self_check:
        run_id, model = args.self_check
        result = self_check(args.runs_dir / run_id, model, cfg)
        print(json.dumps(result, indent=2))
        return 2 if "not_enough_data" in result else 0 if result["no_difference"] else 1
    if args.report is None:
        parser.error("give a score report or --self-check")

    baseline_id = json.loads(args.baseline.read_text())["model"]
    report = json.loads(args.report.read_text())
    verdicts = compare(report, baseline_id, cfg)

    models_text = args.models_file.read_text()
    build_ids = [e["id"] for e in json.loads(models_text)["build"]]
    promoted = [m for m in build_ids if verdicts.get(m, {}).get("promote") and build_ids.index(m) > build_ids.index(baseline_id)]
    gate_report = {"run_id": report["run_id"], "date": args.date, "baseline": baseline_id, "config": cfg, "verdicts": verdicts, "promoted": promoted}
    args.out_dir.joinpath("reports").mkdir(parents=True, exist_ok=True)
    args.out_dir.joinpath("reports", f"gate-{report['run_id']}.json").write_text(json.dumps(gate_report, indent=2) + "\n")

    if promoted:
        proposed = propose(models_text, promoted, baseline_id)
        proposals = args.out_dir / "proposals"
        proposals.mkdir(parents=True, exist_ok=True)
        (proposals / f"{args.date}-models.json").write_text(proposed)
        diff = difflib.unified_diff(
            models_text.splitlines(True), proposed.splitlines(True), "coordinator/models.json", f"proposals/{args.date}-models.json"
        )
        (proposals / f"{args.date}-models.diff").write_text("".join(diff))
    print(json.dumps(gate_report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
