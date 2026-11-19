#!/usr/bin/env python3
"""Run each ladder model on each task through `heavy harbor run -a pi`."""

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
TASKS_DIR = ROOT / "evals" / "harbor" / "tasks"
TASK_SET = ROOT / "evals" / "harbor" / "sets" / "ladder.json"
MODELS_FILE = ROOT / "coordinator" / "models.json"


def load_tasks(selected):
    if TASK_SET.exists():
        listed = json.loads(TASK_SET.read_text())
        listed = listed["tasks"] if isinstance(listed, dict) else listed
        tasks = [
            {"id": t["id"], "type": t.get("type", "untyped"), "heldout": bool(t.get("heldout", False)), "group": t.get("group")}
            for t in listed
        ]
        if selected:
            unknown = sorted(set(selected) - {t["id"] for t in tasks})
            if unknown:
                sys.exit(f"run: not in {TASK_SET.relative_to(ROOT)}: {', '.join(unknown)}")
            tasks = [t for t in tasks if t["id"] in selected]
    elif selected:
        tasks = [{"id": t, "type": "untyped", "heldout": False, "group": None} for t in selected]
    else:
        sys.exit(f"run: {TASK_SET.relative_to(ROOT)} is missing; the eval-set PR provides it. Pass --tasks to run named tasks without it.")
    missing = [t["id"] for t in tasks if not (TASKS_DIR / t["id"]).is_dir()]
    if missing:
        sys.exit(f"run: no task folder under evals/harbor/tasks for: {', '.join(missing)}")
    return tasks


def pick_models(spec, providers):
    data = json.loads(MODELS_FILE.read_text())
    listed = data.get(spec)
    if listed is None:
        wanted = spec.split(",")
        listed = [e for name in ("build", "fix", "review", "panel") for e in data[name] if e["id"] in wanted]
        listed = list({e["id"]: e for e in listed}.values())
    reachable, unreachable = [], []
    for entry in listed:
        model = entry["selection"]["model"]
        provider, _, name = model.partition("/")
        if not name:
            unreachable.append({"id": entry["id"], "reason": f"{model} is not a pi provider/model string"})
        elif provider not in providers:
            unreachable.append({"id": entry["id"], "reason": f"no endpoint for provider {provider} in providers.json"})
        else:
            reachable.append({"id": entry["id"], "model": name, **providers[provider]})
    return reachable, unreachable


def harbor_command(model, task_id, repeats, out_dir):
    return [
        "heavy", "harbor", "run",
        "-p", str(TASKS_DIR / task_id),
        "-a", "pi",
        "-m", model["model"],
        "--base-url", model["base_url"],
        "--api-format", model["api_format"],
        "--api-key-name", model["api_key_name"],
        "-k", str(repeats),
        "-n", "1",
        "-o", str(out_dir),
        "-y",
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default="build", help="a models.json list name or comma-separated ids")
    parser.add_argument("--tasks", type=lambda s: s.split(","), default=[], help="comma-separated task ids")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--run-id", default=datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    tasks = load_tasks(args.tasks)
    reachable, unreachable = pick_models(args.models, json.loads((HERE / "providers.json").read_text()))
    run_dir = HERE / "runs" / args.run_id
    plan = [(m, t) for m in reachable for t in tasks]

    print(f"run {args.run_id}: {len(reachable)} reachable models, {len(tasks)} tasks, {args.repeats} repeats")
    print(f"{len(plan)} harbor jobs, {len(plan) * args.repeats} trials")
    for m in reachable:
        print(f"reachable: {m['id']} -> {m['model']} (key env {m['api_key_name']})")
    for u in unreachable:
        print(f"unreachable: {u['id']}: {u['reason']}")
    if args.dry_run:
        for m, t in plan:
            print(" ".join(harbor_command(m, t["id"], args.repeats, run_dir / m["id"] / t["id"])))
        return 0

    missing_keys = sorted({m["api_key_name"] for m in reachable if not os.environ.get(m["api_key_name"])})
    if missing_keys:
        sys.exit(f"run: set these environment variables first: {', '.join(missing_keys)}")
    run_dir.mkdir(parents=True)
    record = {
        "run_id": args.run_id,
        "repeats": args.repeats,
        "models": [{"id": m["id"], "model": m["model"], "quota_unit": m["quota_unit"], "quota_unit_confirmed": m["quota_unit_confirmed"]} for m in reachable],
        "unreachable": unreachable,
        "tasks": tasks,
    }
    (run_dir / "run.json").write_text(json.dumps(record, indent=2) + "\n")
    short = []
    for m, t in plan:
        out_dir = run_dir / m["id"] / t["id"]
        out_dir.mkdir(parents=True, exist_ok=True)
        code = subprocess.run(harbor_command(m, t["id"], args.repeats, out_dir), check=False).returncode
        trials = len(list(out_dir.glob("*/*/result.json")))
        if code or trials != args.repeats:
            short.append(f"{m['id']}/{t['id']}: exit {code}, {trials} of {args.repeats} trials")
    if short:
        sys.exit("run: these jobs did not complete their trials; do not score this run: " + "; ".join(short))
    return 0


if __name__ == "__main__":
    sys.exit(main())
