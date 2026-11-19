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
TASKS = [{"id": f"t{i:02d}", "type": "bugfix" if i % 2 else "feature", "heldout": i % 4 == 3, "group": None} for i in range(18)]
IDS = [t["id"] for t in TASKS]
REQUESTS = {"minimax": 10, "glm": 10}
TOKENS = (10000, 1000)


def pattern(passing, repeats=3):
    return {i: [1.0] * repeats if i in passing else [0.0] * repeats for i in IDS}


BASE = pattern(IDS[:9])


def write_trial(run_dir, model, task, index, reward, requests, tokens, trajectory=True):
    result = copy.deepcopy(TEMPLATE)
    result["trial_name"] = f"{task}__{model}{index}"
    result["verifier_result"] = {"rewards": {"reward": reward}}
    result["agent_result"].update(n_input_tokens=tokens[0], n_cache_tokens=0, n_output_tokens=tokens[1], cost_usd=None)
    path = run_dir / model / task / "2026-11-19__10-00-00" / f"{result['trial_name']}"
    (path / "agent").mkdir(parents=True)
    (path / "result.json").write_text(json.dumps(result))
    if trajectory:
        trial = copy.deepcopy(TRAJECTORY)
        agent_step = next(s for s in trial["steps"] if s["source"] == "agent")
        trial["steps"] = [s for s in trial["steps"] if s["source"] != "agent"] + [agent_step] * requests
        (path / "agent/trajectory.json").write_text(json.dumps(trial))


def make_run(root, run_id, outcomes, tasks=TASKS, units=None, confirmed=False, requests=None, repeats=3):
    """outcomes: model -> {task id: rewards per repeat}. Baseline and candidates share one run."""
    run_dir = root / "runs" / run_id
    for model, per_task in outcomes.items():
        for task in tasks:
            for i, reward in enumerate(per_task[task["id"]]):
                write_trial(run_dir, model, task["id"], i, reward, (requests or REQUESTS)[model], TOKENS)
    models = [{"id": m, "model": m, "quota_unit": (units or {}).get(m, "requests"), "quota_unit_confirmed": confirmed} for m in outcomes]
    (run_dir / "run.json").write_text(json.dumps({"run_id": run_id, "repeats": repeats, "models": models, "unreachable": [], "tasks": tasks}))
    score.main([str(run_dir), "--out-dir", str(root / "reports")])
    return root / "reports" / f"{run_id}.json"


def run_gate(root, report, date="2026-11-19"):
    pin = root / "baseline.json"
    pin.write_text(json.dumps({"model": "minimax"}))
    gate.main([str(report), "--baseline", str(pin), "--out-dir", str(root), "--date", date])
    verdict = json.loads((root / "reports" / f"gate-{json.loads(report.read_text())['run_id']}.json").read_text())
    return verdict, (root / "proposals" / f"{date}-models.json").exists()


def show(verdict):
    v = verdict["verdicts"]["glm"]
    lo, hi = v["interval_90"]
    return f"diff {v['difference']:+.3f}, 90% [{lo:+.3f}, {hi:+.3f}], half-width {v['interval_half_width']:.3f}, promote={v['promote']}: {v['reason']}"


CASES = {}


def case(name):
    def register(fn):
        CASES[name] = fn
        return fn
    return register


@case("a clear 30-point gain promotes")
def a(root):
    verdict, proposed = run_gate(root, make_run(root, "r1", {"minimax": BASE, "glm": pattern(IDS[:15])}))
    order = [e["id"] for e in json.loads((root / "proposals/2026-11-19-models.json").read_text())["build"]]
    assert proposed and verdict["promoted"] == ["glm"] and order[:2] == ["glm", "minimax"], order
    return show(verdict) + f"; build order {order}"


@case("b a 10-point gain on 18 tasks does not promote and reports its interval")
def b(root):
    verdict, proposed = run_gate(root, make_run(root, "r1", {"minimax": BASE, "glm": pattern(IDS[:11])}))
    v = verdict["verdicts"]["glm"]
    assert not proposed and v["difference"] > 0.10 and v["interval_90"][0] <= 0
    return show(verdict)


@case("c identical models show no difference")
def c(root):
    verdict, proposed = run_gate(root, make_run(root, "r1", {"minimax": BASE, "glm": BASE}))
    v = verdict["verdicts"]["glm"]
    assert not proposed and v["difference"] == 0 and v["interval_90"] == [0, 0]
    return show(verdict)


@case("d a quota-only win with unconfirmed units does not promote")
def d(root):
    verdict, proposed = run_gate(root, make_run(root, "r1", {"minimax": BASE, "glm": BASE}, requests={"minimax": 10, "glm": 5}))
    assert not proposed and "unconfirmed" in verdict["verdicts"]["glm"]["reason"]
    return show(verdict)


@case("e a quota-only win with confirmed units inside the tie band promotes")
def e(root):
    verdict, proposed = run_gate(root, make_run(root, "r1", {"minimax": BASE, "glm": BASE}, confirmed=True, requests={"minimax": 10, "glm": 5}))
    assert proposed and verdict["promoted"] == ["glm"]
    return show(verdict)


@case("f self-check: the same model twice reports no difference, and a drifting model fails it")
def f(root):
    steady = {i: [1.0, 0.0, 0.0, 1.0] if n % 2 else [0.0, 1.0, 1.0, 0.0] for n, i in enumerate(IDS)}
    make_run(root, "r1", {"glm": steady}, repeats=4)
    ok = gate.self_check(root / "runs" / "r1", "glm", json.loads((ROOT / "evals/ladder/gate.json").read_text()))
    drift = {i: [1.0, 0.0, 1.0, 0.0] for i in IDS}
    make_run(root, "r2", {"glm": drift}, repeats=4)
    bad = gate.self_check(root / "runs" / "r2", "glm", json.loads((ROOT / "evals/ladder/gate.json").read_text()))
    assert ok["no_difference"] and not bad["no_difference"]
    assert gate.main(["--self-check", "r1", "glm", "--runs-dir", str(root / "runs")]) == 0
    return {"steady model": ok["interval_90"], "drifting model": bad["interval_90"]}


@case("g tasks sharing a group count as one cluster")
def g(root):
    grouped = [{**t, "group": f"g{n // 3}"} for n, t in enumerate(TASKS)]
    candidate = pattern(IDS[:11])
    verdict, _ = run_gate(root, make_run(root, "r1", {"minimax": BASE, "glm": candidate}, tasks=grouped))
    assert verdict["verdicts"]["glm"]["clusters"] == 6
    return show(verdict)


@case("h flaky task detected")
def h(root):
    flaky = {**BASE, "t00": [1.0, 0.0, 1.0]}
    path = make_run(root, "r1", {"minimax": BASE, "glm": flaky})
    found = json.loads(path.read_text())["models"]["glm"]["flaky_tasks"]
    assert found == [{"task": "t00", "correct": 2, "runs": 3}]
    return found


@case("i a run short of its scheduled trials is not scored")
def i(root):
    make_run(root, "r1", {"minimax": BASE, "glm": BASE})
    sorted((root / "runs" / "r1" / "glm" / "t05").glob("*/*/result.json"))[0].unlink()
    try:
        score.main([str(root / "runs" / "r1"), "--out-dir", str(root / "reports")])
    except SystemExit as err:
        assert "glm/t05: 2 of 3 trials" in str(err), err
        return str(err)
    raise AssertionError("a run with 2 of 3 trials was scored")


@case("j self-check with incomplete or too few repeats reports not enough data")
def j(root):
    cfg = json.loads((ROOT / "evals/ladder/gate.json").read_text())
    make_run(root, "r1", {"glm": BASE})
    few = gate.self_check(root / "runs" / "r1", "glm", cfg)
    make_run(root, "r2", {"glm": pattern(IDS, 4)}, repeats=4)
    for victim in sorted((root / "runs" / "r2" / "glm" / "t00").glob("*/*/result.json"))[:2]:
        victim.unlink()
    short = gate.self_check(root / "runs" / "r2", "glm", cfg)
    assert "not_enough_data" in few and not few["no_difference"] and "not_enough_data" in short, (few, short)
    assert gate.main(["--self-check", "r1", "glm", "--runs-dir", str(root / "runs")]) == 2
    return {"3 repeats": few["not_enough_data"], "2 of 4 retained": short["not_enough_data"]}


@case("k an ungrouped task id and another task's group name stay separate clusters")
def k(root):
    tasks = [{"id": "parser", "type": "bugfix", "heldout": False, "group": None}, {"id": "t01", "type": "bugfix", "heldout": False, "group": "parser"}]
    outcomes = {"minimax": {"parser": [0.0] * 3, "t01": [1.0] * 3}, "glm": {"parser": [1.0] * 3, "t01": [1.0] * 3}}
    verdict, proposed = run_gate(root, make_run(root, "r1", outcomes, tasks=tasks))
    assert verdict["verdicts"]["glm"]["clusters"] == 2 and not proposed
    return show(verdict)


@case("l a zero baseline quota per correct answer still writes a report")
def l(root):
    verdict, proposed = run_gate(root, make_run(root, "r1", {"minimax": BASE, "glm": BASE}, confirmed=True, requests={"minimax": 0, "glm": 5}))
    assert not proposed and "not comparable" in verdict["verdicts"]["glm"]["reason"]
    return show(verdict)


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
