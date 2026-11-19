#!/usr/bin/env python3
"""Decide whether candidates move up the build list; propose, never apply."""

import argparse
import datetime
import difflib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
EPSILON = 1e-9


def covered(report):
    """The task set, split and repeat count a report ran, or None when the report does not say."""
    tasks = report.get("tasks")
    if tasks is None:
        return None
    return report.get("repeats"), sorted((t["id"], bool(t.get("heldout", False))) for t in tasks)


def judge(candidate, baseline, cfg):
    train, held = candidate["train"], candidate["heldout"]
    base_train, base_held = baseline["train"], baseline["heldout"]
    if any(s["cost_status"] != "OK" for s in (train, base_train, held, base_held)):
        return False, "cost UNVERIFIED on the compared tasks"
    if None in (held["pass_rate"], base_held["pass_rate"]):
        return False, "no held-out runs to compare"
    if base_train["correct_per_dollar"] <= 0:
        return False, "the baseline got nothing correct on the non-held-out tasks"
    ratio = train["correct_per_dollar"] / base_train["correct_per_dollar"]
    if ratio < cfg["min_cpd_ratio"] - EPSILON:
        return False, f"correct per dollar is {ratio:.2f}x the baseline, need {cfg['min_cpd_ratio']}x"
    if train["pass_rate"] < base_train["pass_rate"] - cfg["max_pass_drop"] - EPSILON:
        return False, "pass rate dropped on the non-held-out tasks"
    if held["pass_rate"] < base_held["pass_rate"] - cfg["max_pass_drop"] - EPSILON:
        return False, "pass rate dropped on the held-out tasks"
    return True, f"wins clearly at {ratio:.2f}x correct per dollar"


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
    parser.add_argument("reports", nargs="+", type=Path, help="score reports, oldest first")
    parser.add_argument("--baseline", type=Path, default=HERE / "baseline.json")
    parser.add_argument("--gate", type=Path, default=HERE / "gate.json")
    parser.add_argument("--models-file", type=Path, default=ROOT / "coordinator" / "models.json")
    parser.add_argument("--out-dir", type=Path, default=HERE)
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    args = parser.parse_args(argv)

    cfg = json.loads(args.gate.read_text())
    pin = json.loads(args.baseline.read_text())
    if not pin.get("report"):
        sys.exit("gate: baseline.json has no pinned report yet; score a baseline run and pin it")
    baseline_path = Path(pin["report"])
    baseline_path = baseline_path if baseline_path.is_absolute() else args.baseline.parent / baseline_path
    baseline_report = json.loads(baseline_path.read_text())
    baseline = baseline_report["models"].get(pin["model"])
    if baseline is None:
        sys.exit(f"gate: the pinned report has no entry for {pin['model']}")
    reports, seen = [], set()
    for path in args.reports:
        report = json.loads(path.read_text())
        if report["run_id"] in seen:
            continue
        seen.add(report["run_id"])
        reports.append(report)

    need = cfg["consecutive_reports"]
    candidates = sorted({m for r in reports for m in r["models"]} - {pin["model"]})
    verdicts = {}
    baseline_cover = covered(baseline_report)
    for model in candidates:
        per_report = []
        for r in reports:
            if model not in r["models"]:
                ok, why = False, "not measured"
            elif baseline_cover is None or covered(r) != baseline_cover:
                ok, why = False, "ran a different task set or split from the baseline"
            else:
                ok, why = judge(r["models"][model], baseline, cfg)
            per_report.append({"run_id": r["run_id"], "wins_clearly": ok, "reason": why})
        tail = per_report[-need:]
        verdicts[model] = {
            "reports": per_report,
            "promote": len(tail) == need and all(v["wins_clearly"] for v in tail),
        }

    models_text = args.models_file.read_text()
    build_ids = [e["id"] for e in json.loads(models_text)["build"]]
    promoted = [m for m in build_ids if verdicts.get(m, {}).get("promote") and build_ids.index(m) > build_ids.index(pin["model"])]
    gate_report = {"date": args.date, "baseline": pin["model"], "config": cfg, "verdicts": verdicts, "promoted": promoted}
    args.out_dir.joinpath("reports").mkdir(parents=True, exist_ok=True)
    args.out_dir.joinpath("reports", f"gate-{args.date}.json").write_text(json.dumps(gate_report, indent=2) + "\n")

    if promoted:
        proposed = propose(models_text, promoted, pin["model"])
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
