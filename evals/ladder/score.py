#!/usr/bin/env python3
"""Score a ladder run directory into reports/<run-id>.json and .md."""

import argparse
import hashlib
import json
import random
import shlex
import statistics
import subprocess
import sys
from datetime import datetime, timedelta, timezone
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


BUILTIN_ARMS = ("random", "first-option", "recorded")
OUTCOME_CHECKS = ("reverted", "main_broke", "rollback_or_incident", "recut")
STANCE = {
    **dict.fromkeys(("yes", "yes, merge", "approve", "approve all", "merge", "release", "ship", "promote now", "gate it whole", "keep", "keep it as one pr"), "approve"),
    **dict.fromkeys(("no", "hold", "hold until the freeze lifts", "revert", "wait"), "reject"),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def norm(s):
    return " ".join(str(s).split()).casefold()


def read_cases(labels_dir, split_key):
    labels_dir = Path(labels_dir)
    wanted = set(json.loads((labels_dir / "split.json").read_text())[split_key])
    cases, unscored = [], 0
    for line in (labels_dir / "labels.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        try:
            label = json.loads(line)
        except json.JSONDecodeError:
            continue
        if label.get("id") not in wanted:
            continue
        options = label.get("options") or []
        if options and norm(label.get("answer")) in {norm(o) for o in options}:
            cases.append(label)
        else:
            unscored += 1
    return cases, unscored


def read_outcomes(labels_dir):
    path = Path(labels_dir) / "outcomes.jsonl"
    rows = {}
    for line in path.read_text().splitlines() if path.exists() else []:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows[row["id"]] = row
    return rows


def outcome_correct(chosen, row):
    stance = STANCE.get(norm(chosen))
    checks = [row.get(k) for k in OUTCOME_CHECKS] if row else []
    if stance is None or all(c is None for c in checks):
        return None
    went_wrong = any(c is True for c in checks)
    return went_wrong if stance == "reject" else not went_wrong


def outcome_summary(detail, key):
    values = [d[key] for d in detail if d[key] is not None]
    return {"scored": len(values), "correct": sum(values), "rate": sum(values) / len(values) if values else None}


def pick(arm_name, arm_cmd, case, repeat):
    shuffled = list(case["options"])
    random.Random(f"{case['id']}:{repeat}").shuffle(shuffled)
    if arm_name == "random":
        return random.Random(f"pick:{case['id']}:{repeat}").choice(shuffled)
    if arm_name == "first-option":
        return shuffled[0]
    if arm_name == "recorded":
        return case["recommended_option"]
    payload = {"id": case["id"], "kind": case["kind"], "item_text": case["item_text"], "options": shuffled}
    done = subprocess.run(shlex.split(arm_cmd), input=json.dumps(payload), capture_output=True, text=True, check=True, timeout=300)
    return done.stdout.strip()


def locked_score(labels_dir, split_key, arm, arm_cmd, baseline, baseline_cmd, repeats):
    cases, unscored = read_cases(labels_dir, split_key)
    outcomes = read_outcomes(labels_dir)
    per_case, detail = [], []
    for case in cases:
        answer = norm(case["answer"])
        hits = []
        for repeat in range(repeats):
            arm_pick = pick(arm, arm_cmd, case, repeat)
            baseline_pick = pick(baseline, baseline_cmd, case, repeat)
            a, b = norm(arm_pick) == answer, norm(baseline_pick) == answer
            hits.append((a, b))
            row = outcomes.get(case["id"])
            detail.append({
                "id": case["id"], "repeat": repeat, "arm": a, "baseline": b,
                "arm_outcome": outcome_correct(arm_pick, row), "baseline_outcome": outcome_correct(baseline_pick, row),
            })
        per_case.append(sum(a - b for a, b in hits) / repeats)
    n = len(per_case)
    lift = statistics.mean(per_case) * 100 if n else 0.0
    paired_se = statistics.stdev(per_case) / n ** 0.5 * 100 if n > 1 else 0.0
    repeat_scores = []
    for repeat in range(repeats if n else 0):
        rows = [d for d in detail if d["repeat"] == repeat]
        a = 100 * sum(d["arm"] for d in rows) / n
        b = 100 * sum(d["baseline"] for d in rows) / n
        repeat_scores.append({"arm": a, "baseline": b, "lift": a - b})
    return {
        "repeat_scores": repeat_scores,
        "lift": lift,
        "paired_se": paired_se,
        "beats_noise": lift > 2 * paired_se,
        "min_detectable_lift": 2 * paired_se,
        "unscored": unscored,
        "baseline": baseline,
        "arm": arm,
        "n": n,
        "outcome_correct": {
            "arm": outcome_summary(detail, "arm_outcome"),
            "baseline": outcome_summary(detail, "baseline_outcome"),
            "cases_with_outcome": sum(1 for c in cases if any((outcomes.get(c["id"]) or {}).get(k) is not None for k in OUTCOME_CHECKS)),
        },
        "per_case": detail,
    }


def lock_hashes(labels_dir):
    labels_dir = Path(labels_dir)
    hashes = {
        "labels": sha(labels_dir / "labels.jsonl"),
        "split": sha(labels_dir / "split.json"),
        "scorer": sha(__file__),
    }
    if (labels_dir / "outcomes.jsonl").exists():
        hashes["outcomes"] = sha(labels_dir / "outcomes.jsonl")
    return hashes


def recent_final(path):
    if not path.exists():
        return None
    now = datetime.now(timezone.utc)
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = datetime.fromisoformat(row["ts"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if now - ts < timedelta(days=7):
            return row["ts"]
    return None


def append_final(path, result):
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "arm": result["arm"],
        "baseline": result["baseline"],
        "lift": result["lift"],
    }
    with path.open("a") as handle:
        handle.write(json.dumps(row) + "\n")


def run_locked(args, split_key):
    if not args.lock.exists():
        print(f"score: no lock at {args.lock}; run `score.py lock --labels {args.labels}`", file=sys.stderr)
        return 3
    if json.loads(args.lock.read_text()) != lock_hashes(args.labels):
        print(f"score: lock at {args.lock} does not match the labels, split or scorer", file=sys.stderr)
        return 3
    if args.command == "final":
        seen = recent_final(args.final_log)
        if seen:
            print(f"score: the final split was checked at {seen}; wait 7 days", file=sys.stderr)
            return 5
    result = locked_score(args.labels, split_key, args.arm, args.arm_cmd, args.baseline, args.baseline_cmd, args.repeats)
    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + "\n")
    if args.command == "final":
        append_final(args.final_log, result)
    print(f"{result['lift']:.2f}")
    oc = result["outcome_correct"]
    fmt = lambda s: "n/a" if s["rate"] is None else f"{s['rate']:.1%} ({s['correct']}/{s['scored']})"
    print(f"outcome_correct arm {fmt(oc['arm'])} baseline {fmt(oc['baseline'])} coverage {oc['cases_with_outcome']}/{result['n']} cases", file=sys.stderr)
    return 0


def cli(argv):
    parser = argparse.ArgumentParser(prog="score.py")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("locked", "final"):
        p = sub.add_parser(name)
        p.add_argument("--labels", type=Path, required=True)
        p.add_argument("--arm", required=True)
        p.add_argument("--arm-cmd")
        p.add_argument("--baseline", required=True)
        p.add_argument("--baseline-cmd")
        p.add_argument("--repeats", type=int, default=5)
        p.add_argument("--json", type=Path)
        p.add_argument("--lock", type=Path, default=HERE / "score.lock")
        p.add_argument("--final-log", type=Path, default=HERE / "final_checks.jsonl")
    lock = sub.add_parser("lock")
    lock.add_argument("--labels", type=Path, required=True)
    lock.add_argument("--lock", type=Path, default=HERE / "score.lock")
    args = parser.parse_args(argv)
    if args.command != "lock":
        for role in ("arm", "baseline"):
            if getattr(args, role) not in BUILTIN_ARMS and not getattr(args, f"{role}_cmd"):
                parser.error(f"--{role} {getattr(args, role)} is not built in; pass --{role}-cmd")
    if args.command == "lock":
        args.lock.write_text(json.dumps(lock_hashes(args.labels), indent=2) + "\n")
        return 0
    return run_locked(args, "heldout" if args.command == "locked" else "final")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] in ("locked", "final", "lock"):
        return cli(argv)
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
