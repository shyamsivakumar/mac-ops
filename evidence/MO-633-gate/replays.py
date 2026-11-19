#!/usr/bin/env python3
"""Replay the scorer and gate on fixture run dirs shaped like real Harbor 0.26.0 job output."""

import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evals" / "ladder"))
import gate
import score

REAL = next((ROOT / "evals/harbor/logs/pi-run").glob("*/example__*/result.json"))
TEMPLATE = json.loads(REAL.read_text())
TASKS = [
    {"id": "alpha-1", "type": "bugfix", "heldout": False},
    {"id": "alpha-2", "type": "bugfix", "heldout": False},
    {"id": "beta-3", "type": "feature", "heldout": False},
    {"id": "beta-4", "type": "feature", "heldout": True},
]
PRICES = {
    "glm": {"input_per_mtok": 1.0, "cache_read_per_mtok": 0.1, "output_per_mtok": 2.0, "source": "fixture"},
    "deepseek": {"input_per_mtok": None, "cache_read_per_mtok": None, "output_per_mtok": None, "source": "fixture"},
}


def write_trial(run_dir, model, task, index, reward, cost_usd):
    result = copy.deepcopy(TEMPLATE)
    result["trial_name"] = f"{task}__{model}{index}"
    result["verifier_result"] = {"rewards": {"reward": reward}}
    result["agent_result"].update(n_input_tokens=10000, n_cache_tokens=0, n_output_tokens=1000, cost_usd=cost_usd)
    path = run_dir / model / task / "2026-11-19__10-00-00" / result["trial_name"]
    path.mkdir(parents=True)
    (path / "result.json").write_text(json.dumps(result))


def make_run(root, run_id, outcomes, tasks=TASKS, costs=None):
    """outcomes: model -> {task id: list of rewards}; a missing task means all pass."""
    run_dir = root / "runs" / run_id
    for model, per_task in outcomes.items():
        for task in tasks:
            rewards = per_task.get(task["id"], [1.0, 1.0, 1.0])
            for i, reward in enumerate(rewards):
                cost = (costs or {}).get(model, {}).get(task["id"], 0.10 if model == "minimax" else None)
                write_trial(run_dir, model, task["id"], i, reward, cost)
    models = [{"id": model, "model": model} for model in outcomes]
    (run_dir / "run.json").write_text(json.dumps({"run_id": run_id, "repeats": 3, "models": models, "unreachable": [], "tasks": tasks}))
    prices = root / "prices.json"
    prices.write_text(json.dumps(PRICES))
    score.main([str(run_dir), "--prices", str(prices), "--out-dir", str(root / "reports")])
    return root / "reports" / f"{run_id}.json"


def run_gate(root, reports, date, baseline_outcomes=None, baseline_tasks=TASKS):
    baseline = make_run(root, "baseline", baseline_outcomes or {"minimax": {}}, tasks=baseline_tasks)
    pin = root / "baseline.json"
    pin.write_text(json.dumps({"model": "minimax", "report": str(baseline)}))
    gate.main([*map(str, reports), "--baseline", str(pin), "--gate", str(ROOT / "evals/ladder/gate.json"), "--out-dir", str(root), "--date", date])
    verdict = json.loads((root / "reports" / f"gate-{date}.json").read_text())
    return verdict, (root / "proposals" / f"{date}-models.json").exists()


WIN = {"glm": {}}
CASES = {}


def case(name):
    def register(fn):
        CASES[name] = fn
        return fn
    return register


@case("a clear win twice writes a proposal")
def a(root):
    reports = [make_run(root, "r1", WIN), make_run(root, "r2", WIN)]
    verdict, proposed = run_gate(root, reports, "2026-11-19")
    diff = (root / "proposals" / "2026-11-19-models.diff").read_text()
    assert proposed and verdict["promoted"] == ["glm"]
    order = [e["id"] for e in json.loads((root / "proposals/2026-11-19-models.json").read_text())["build"]]
    assert order[:2] == ["glm", "minimax"], order
    return f"promoted {verdict['promoted']}, build order {order}; diff {len(diff.splitlines())} lines"


@case("b clear win once writes no proposal")
def b(root):
    losing = {"glm": {"alpha-1": [0.0, 0.0, 0.0]}}
    reports = [make_run(root, "r1", losing), make_run(root, "r2", WIN)]
    verdict, proposed = run_gate(root, reports, "2026-11-19")
    assert not proposed and verdict["promoted"] == []
    return [v["wins_clearly"] for v in verdict["verdicts"]["glm"]["reports"]]


@case("c higher cpd but pass-rate drop writes no proposal")
def c(root):
    dropped = {"glm": {"alpha-1": [1.0, 0.0, 1.0]}}
    reports = [make_run(root, "r1", dropped), make_run(root, "r2", dropped)]
    verdict, proposed = run_gate(root, reports, "2026-11-19")
    assert not proposed
    return verdict["verdicts"]["glm"]["reports"][-1]["reason"]


@case("d win on training slice but loss on held-out writes no proposal")
def d(root):
    held_loss = {"glm": {"beta-4": [0.0, 0.0, 1.0]}}
    reports = [make_run(root, "r1", held_loss), make_run(root, "r2", held_loss)]
    verdict, proposed = run_gate(root, reports, "2026-11-19")
    assert not proposed
    return verdict["verdicts"]["glm"]["reports"][-1]["reason"]


@case("e flaky task detected")
def e(root):
    path = make_run(root, "r1", {"glm": {"alpha-2": [1.0, 0.0, 1.0]}})
    flaky = json.loads(path.read_text())["models"]["glm"]["flaky_tasks"]
    assert flaky == [{"task": "alpha-2", "correct": 2, "runs": 3}]
    return flaky


@case("f missing price marks cost UNVERIFIED and blocks promotion")
def f(root):
    both = {"glm": {}, "deepseek": {}}
    reports = [make_run(root, "r1", both), make_run(root, "r2", both)]
    verdict, proposed = run_gate(root, reports, "2026-11-19")
    report = json.loads(reports[0].read_text())["models"]["deepseek"]
    assert report["cost_status"] == "UNVERIFIED" and report["cost_per_correct"] is None
    assert verdict["promoted"] == ["glm"] and not verdict["verdicts"]["deepseek"]["promote"]
    assert [e["id"] for e in json.loads((root / "proposals/2026-11-19-models.json").read_text())["build"]].count("deepseek") == 1
    return {"deepseek": verdict["verdicts"]["deepseek"]["reports"][-1]["reason"], "promoted": verdict["promoted"]}


@case("g the same winning report passed twice writes no proposal")
def g(root):
    report = make_run(root, "r1", WIN)
    verdict, proposed = run_gate(root, [report, report], "2026-11-19")
    assert not proposed and verdict["promoted"] == []
    return [v["run_id"] for v in verdict["verdicts"]["glm"]["reports"]]


@case("h a win on fewer tasks than the baseline writes no proposal")
def h(root):
    easy = [t for t in TASKS if t["id"] in ("alpha-1", "beta-4")]
    reports = [make_run(root, "r1", WIN, tasks=easy), make_run(root, "r2", WIN, tasks=easy)]
    verdict, proposed = run_gate(root, reports, "2026-11-19")
    assert not proposed and verdict["promoted"] == []
    return verdict["verdicts"]["glm"]["reports"][-1]["reason"]


@case("i a baseline with no correct training answers writes no proposal")
def i(root):
    nothing = {"minimax": {t["id"]: [0.0, 0.0, 0.0] for t in TASKS if not t["heldout"]}}
    reports = [make_run(root, "r1", WIN), make_run(root, "r2", WIN)]
    verdict, proposed = run_gate(root, reports, "2026-11-19", baseline_outcomes=nothing)
    assert not proposed and verdict["promoted"] == []
    return verdict["verdicts"]["glm"]["reports"][-1]["reason"]


@case("j a win with UNVERIFIED held-out cost writes no proposal")
def j(root):
    half_priced = {"deepseek": {t["id"]: 0.10 for t in TASKS if not t["heldout"]}}
    reports = [make_run(root, "r1", {"deepseek": {}}, costs=half_priced),
               make_run(root, "r2", {"deepseek": {}}, costs=half_priced)]
    verdict, proposed = run_gate(root, reports, "2026-11-19")
    report = json.loads(reports[0].read_text())["models"]["deepseek"]
    assert report["train"]["cost_status"] == "OK" and report["heldout"]["cost_status"] == "UNVERIFIED"
    assert not proposed and verdict["promoted"] == []
    return verdict["verdicts"]["deepseek"]["reports"][-1]["reason"]


@case("k a run short of its scheduled trials is not scored")
def k(root):
    make_run(root, "r1", {"glm": {}})
    lost = sorted((root / "runs" / "r1" / "glm" / "beta-3").glob("*/*/result.json"))[0]
    lost.unlink()
    try:
        score.main([str(root / "runs" / "r1"), "--prices", str(root / "prices.json"), "--out-dir", str(root / "reports")])
    except SystemExit as err:
        assert "glm/beta-3: 2 of 3 trials" in str(err), err
        return str(err)
    raise AssertionError("a run with 2 of 3 trials was scored")


if __name__ == "__main__":
    failures = 0
    for name, fn in CASES.items():
        with tempfile.TemporaryDirectory() as tmp:
            try:
                print(f"PASS  {name}: {fn(Path(tmp))}")
            except AssertionError as err:
                failures += 1
                print(f"FAIL  {name}: {err!r}")
    sys.exit(1 if failures else 0)
