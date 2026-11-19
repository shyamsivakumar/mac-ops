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

REAL_TRIAL = next((ROOT / "evals/harbor/logs/pi-run").glob("*/example__*"))
TEMPLATE = json.loads((REAL_TRIAL / "result.json").read_text())
TRAJECTORY = json.loads((REAL_TRIAL / "agent/trajectory.json").read_text())
TASKS = [
    {"id": "alpha-1", "type": "bugfix", "heldout": False},
    {"id": "alpha-2", "type": "bugfix", "heldout": False},
    {"id": "beta-3", "type": "feature", "heldout": False},
    {"id": "beta-4", "type": "feature", "heldout": True},
]
REQUESTS = {"minimax": 10, "glm": 5, "deepseek": 5}
TOKENS = {"minimax": (10000, 1000), "glm": (10000, 1000), "deepseek": (10000, 1000)}


def write_trial(run_dir, model, task, index, reward, requests, tokens, trajectory=True):
    result = copy.deepcopy(TEMPLATE)
    result["trial_name"] = f"{task}__{model}{index}"
    result["verifier_result"] = {"rewards": {"reward": reward}}
    result["agent_result"].update(n_input_tokens=tokens[0], n_cache_tokens=0, n_output_tokens=tokens[1], cost_usd=None)
    path = run_dir / model / task / "2026-11-19__10-00-00" / result["trial_name"]
    (path / "agent").mkdir(parents=True)
    (path / "result.json").write_text(json.dumps(result))
    if trajectory:
        trial = copy.deepcopy(TRAJECTORY)
        agent_step = next(s for s in trial["steps"] if s["source"] == "agent")
        trial["steps"] = [s for s in trial["steps"] if s["source"] != "agent"] + [agent_step] * requests
        (path / "agent/trajectory.json").write_text(json.dumps(trial))


def make_run(root, run_id, outcomes, tasks=TASKS, units=None, requests=None, tokens=None, trajectory=True):
    """outcomes: model -> {task id: list of rewards}; a missing task means all pass."""
    run_dir = root / "runs" / run_id
    for model, per_task in outcomes.items():
        for task in tasks:
            for i, reward in enumerate(per_task.get(task["id"], [1.0, 1.0, 1.0])):
                write_trial(run_dir, model, task["id"], i, reward, (requests or REQUESTS)[model], (tokens or TOKENS)[model], trajectory)
    models = [{"id": m, "model": m, "quota_unit": (units or {}).get(m, "requests")} for m in outcomes]
    (run_dir / "run.json").write_text(json.dumps({"run_id": run_id, "repeats": 3, "models": models, "unreachable": [], "tasks": tasks}))
    score.main([str(run_dir), "--out-dir", str(root / "reports")])
    return root / "reports" / f"{run_id}.json"


def run_gate(root, reports, date, baseline_outcomes=None, baseline_tasks=TASKS, baseline_units=None):
    baseline = make_run(root, "baseline", baseline_outcomes or {"minimax": {}}, tasks=baseline_tasks, units=baseline_units)
    pin = root / "baseline.json"
    pin.write_text(json.dumps({"model": "minimax", "report": str(baseline)}))
    gate.main([*map(str, reports), "--baseline", str(pin), "--gate", str(ROOT / "evals/ladder/gate.json"), "--out-dir", str(root), "--date", date])
    verdict = json.loads((root / "reports" / f"gate-{date}.json").read_text())
    return verdict, (root / "proposals" / f"{date}-models.json").exists()


def last_reason(verdict, model="glm"):
    return verdict["verdicts"][model]["reports"][-1]["reason"]


WIN = {"glm": {}}
SLOW = {"minimax": 10, "glm": 10}
WEAK_BASELINE = {"minimax": {"alpha-1": [0.0, 0.0, 0.0]}}
CASES = {}


def case(name):
    def register(fn):
        CASES[name] = fn
        return fn
    return register


@case("a two clear wins on quota write a proposal")
def a(root):
    reports = [make_run(root, "r1", WIN), make_run(root, "r2", WIN)]
    verdict, proposed = run_gate(root, reports, "2026-11-19")
    diff = (root / "proposals" / "2026-11-19-models.diff").read_text()
    order = [e["id"] for e in json.loads((root / "proposals/2026-11-19-models.json").read_text())["build"]]
    assert proposed and verdict["promoted"] == ["glm"] and order[:2] == ["glm", "minimax"], order
    return f"{last_reason(verdict)}; build order {order}; diff {len(diff.splitlines())} lines"


@case("b two clear wins on pass rate write a proposal")
def b(root):
    reports = [make_run(root, "r1", WIN, requests=SLOW), make_run(root, "r2", WIN, requests=SLOW)]
    verdict, proposed = run_gate(root, reports, "2026-11-19", baseline_outcomes=WEAK_BASELINE)
    assert proposed and verdict["promoted"] == ["glm"]
    return last_reason(verdict)


@case("c one clear win writes no proposal")
def c(root):
    losing = {"glm": {"alpha-1": [0.0, 0.0, 0.0]}}
    reports = [make_run(root, "r1", losing), make_run(root, "r2", WIN)]
    verdict, proposed = run_gate(root, reports, "2026-11-19")
    assert not proposed and verdict["promoted"] == []
    return [v["wins_clearly"] for v in verdict["verdicts"]["glm"]["reports"]]


@case("d pass-rate drop with less quota writes no proposal")
def d(root):
    dropped = {"glm": {"alpha-1": [1.0, 0.0, 1.0]}}
    reports = [make_run(root, "r1", dropped), make_run(root, "r2", dropped)]
    verdict, proposed = run_gate(root, reports, "2026-11-19")
    assert not proposed
    return last_reason(verdict)


@case("e held-out loss writes no proposal")
def e(root):
    held_loss = {"glm": {"beta-4": [0.0, 0.0, 1.0]}}
    reports = [make_run(root, "r1", held_loss), make_run(root, "r2", held_loss)]
    verdict, proposed = run_gate(root, reports, "2026-11-19")
    assert not proposed
    return last_reason(verdict)


@case("f flaky task detected")
def f(root):
    path = make_run(root, "r1", {"glm": {"alpha-2": [1.0, 0.0, 1.0]}})
    flaky = json.loads(path.read_text())["models"]["glm"]["flaky_tasks"]
    assert flaky == [{"task": "alpha-2", "correct": 2, "runs": 3}]
    return flaky


@case("g different quota units ignore quota and apply the pass-rate rule only")
def g(root):
    tiny = {"glm": (1000, 100), "minimax": (10000, 1000)}
    kwargs = dict(units={"glm": "tokens"}, tokens=tiny)
    (root / "x").mkdir()
    reports = [make_run(root / "x", "r1", WIN, **kwargs), make_run(root / "x", "r2", WIN, **kwargs)]
    verdict, proposed = run_gate(root / "x", reports, "2026-11-19")
    assert not proposed and "units differ" in last_reason(verdict), last_reason(verdict)
    (root / "y").mkdir()
    reports = [make_run(root / "y", "r1", WIN, **kwargs), make_run(root / "y", "r2", WIN, **kwargs)]
    verdict, proposed = run_gate(root / "y", reports, "2026-11-19", baseline_outcomes=WEAK_BASELINE)
    assert proposed and verdict["promoted"] == ["glm"]
    return {"equal pass rate": "no proposal despite 10x less quota", "pass-rate gain": last_reason(verdict)}


@case("h quota with no trajectory is UNVERIFIED and cannot win")
def h(root):
    reports = [make_run(root, "r1", WIN, trajectory=False), make_run(root, "r2", WIN, trajectory=False)]
    verdict, proposed = run_gate(root, reports, "2026-11-19")
    assert json.loads(reports[0].read_text())["models"]["glm"]["quota_status"] == "UNVERIFIED"
    assert not proposed
    return last_reason(verdict)


@case("i the same winning report passed twice writes no proposal")
def i(root):
    report = make_run(root, "r1", WIN)
    verdict, proposed = run_gate(root, [report, report], "2026-11-19")
    assert not proposed and verdict["promoted"] == []
    return [v["run_id"] for v in verdict["verdicts"]["glm"]["reports"]]


@case("j a win on fewer tasks than the baseline writes no proposal")
def j(root):
    easy = [t for t in TASKS if t["id"] in ("alpha-1", "beta-4")]
    reports = [make_run(root, "r1", WIN, tasks=easy), make_run(root, "r2", WIN, tasks=easy)]
    verdict, proposed = run_gate(root, reports, "2026-11-19")
    assert not proposed and verdict["promoted"] == []
    return last_reason(verdict)


@case("k a baseline with no correct training answers does not crash or promote")
def k(root):
    nothing = {t["id"]: [0.0, 0.0, 0.0] for t in TASKS if not t["heldout"]}
    reports = [make_run(root, "r1", {"glm": nothing}), make_run(root, "r2", {"glm": nothing})]
    verdict, proposed = run_gate(root, reports, "2026-11-19", baseline_outcomes={"minimax": nothing})
    assert not proposed and verdict["promoted"] == []
    return last_reason(verdict)


@case("l a run short of its scheduled trials is not scored")
def l(root):
    make_run(root, "r1", {"glm": {}})
    sorted((root / "runs" / "r1" / "glm" / "beta-3").glob("*/*/result.json"))[0].unlink()
    try:
        score.main([str(root / "runs" / "r1"), "--out-dir", str(root / "reports")])
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
