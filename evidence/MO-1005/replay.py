"""Replay fake snapshots through coord-watch with an isolated HOME and state."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
base = json.loads((root / "evidence/MO-1004/complete.json").read_text())
with tempfile.TemporaryDirectory() as folder:
    folder = Path(folder)
    env = {**os.environ, "HOME": str(folder)}
    def cycle(name, data, state="state"):
        source = folder / "input.json"
        source.write_text(json.dumps(data))
        result = subprocess.run(["python3", str(root / "coordinator/bin/coord-watch"),
            "--config", str(root / "evidence/MO-1004/config.json"),
            "--fake-input", str(source), "--state", str(folder / state)],
            env=env, capture_output=True, text=True, check=True)
        events = [line for line in result.stdout.splitlines() if line.startswith("EVENT ")]
        print(name + ": " + json.dumps(events))
    ready = copy.deepcopy(base)
    ready["github"]["example/project"]["pulls"] = []
    ready["github"]["example/project"]["issues"][0]["labels"] = [{"name": "stage:todo"}]
    ready["queue"]["dispatch-receipts.json"] = {}
    cycle("first idle", ready)
    cycle("second idle, new process", ready)
    cycle("restart dedup", ready)
    stopped = copy.deepcopy(ready)
    stopped["queue"]["dispatch-receipts.json"] = base["queue"]["dispatch-receipts.json"]
    stopped["threads"][0]["status"] = "completed"
    cycle("builder completed", stopped, "builder")
    parked = copy.deepcopy(stopped)
    parked["github"]["example/project"]["issues"][0]["labels"] = [{"name": "stage:backlog"}]
    cycle("parked", parked, "parked")
    with_pr = copy.deepcopy(base)
    with_pr["threads"][0]["status"] = "completed"
    cycle("completed with PR", with_pr, "pr")
    gate = copy.deepcopy(base)
    head = "a" * 40
    gate["queue"]["dispatch-receipts.json"][f"gate:example/project#350:{head}"] = "gate"
    gate["gates"] = [{"repo": "example/project", "pr": 350, "head": head,
                      "thread": "gate", "verdict": "FAIL"}]
    cycle("FAIL", gate, "gate")
    cycle("FAIL restart dedup", gate, "gate")
    head = "b" * 40
    gate["github"]["example/project"]["pulls"][0]["head"]["sha"] = head
    gate["gates"][0]["head"] = head
    gate["queue"]["dispatch-receipts.json"][f"gate:example/project#350:{head}"] = "gate"
    cycle("new head FAIL", gate, "gate")
    partial = copy.deepcopy(stopped)
    partial["threadsComplete"] = False
    cycle("partial read", partial, "partial")
    cycle("idle before partial", ready, "interrupted")
    cycle("partial resets idle", partial, "interrupted")
    cycle("idle after partial", ready, "interrupted")
    missing_gate = copy.deepcopy(ready)
    missing_gate["gates"] = [{"repo": "example/project", "pr": 350,
                              "head": "a" * 40, "thread": "unlisted-gate", "verdict": ""}]
    missing_gate["queue"]["dispatch-receipts.json"][
        "gate:example/project#350:" + "a" * 40] = "unlisted-gate"
    cycle("missing gate first cycle", missing_gate, "missing-gate")
    cycle("missing gate second cycle", missing_gate, "missing-gate")
    missing_gate["threads"].append({"threadId": "unlisted-gate", "status": "completed"})
    cycle("gate terminal first idle", missing_gate, "missing-gate")
    cycle("gate terminal second idle", missing_gate, "missing-gate")
