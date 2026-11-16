"""Reproduce MO-1006 command acceptance with fake sources and isolated HOME."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = json.loads((ROOT / "evidence/MO-1004/complete.json").read_text())
CONFIG = ROOT / "evidence/MO-1004/config.json"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


with tempfile.TemporaryDirectory(prefix="mo-1006-") as temporary:
    home = Path(temporary).resolve()
    env = {**os.environ, "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"}
    source = home / "input.json"
    state = home / "watch.json"
    log = home / "runtime.log"
    marker = "SYNTHETIC_PRIVATE_LINE_DO_NOT_EMIT"
    log.write_text("")
    raw = copy.deepcopy(BASE)
    raw["threads"] = [{"threadId": "builder-343", "status": "running",
                       "runId": "run-one", "startedAt": 1000}]
    executable = ROOT / "coordinator/bin/coord-watch"

    def files():
        return {str(p.relative_to(home)): (p.read_bytes(), stat.S_IMODE(p.stat().st_mode))
                for p in home.rglob("*") if p.is_file()}

    def cycle(name, now, expected):
        raw["now"] = now
        source.write_text(json.dumps(raw))
        before = files()
        result = subprocess.run([str(executable), "--once", "--config", str(CONFIG),
                                 "--fake-input", str(source), "--state", str(state),
                                 "--log", str(log)], env=env, capture_output=True,
                                text=True, timeout=15, check=True)
        after = files()
        changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
        require(changed <= {"watch.json"}, name + ": runtime wrote outside its state")
        require(marker not in result.stdout + result.stderr + state.read_text(),
                name + ": leaked synthetic private marker")
        observed = [line for line in result.stdout.splitlines() if line.startswith("EVENT ")]
        require(observed == expected, name + ": unexpected events " + repr(observed))
        require(sum(line.startswith("BOARD ") for line in result.stdout.splitlines()) == 1,
                name + ": missing BOARD")
        require(result.stderr == "", name + ": unexpected stderr")
        print(name + ": PASS " + json.dumps(observed))

    cycle("below 20 minutes", 2199, [])
    cycle("exactly 20 minutes", 2200, [])
    cycle("over 20 minutes", 2201, ["EVENT run-long builder-343 20"])
    cycle("restart run dedup", 2300, [])
    raw["threads"][0]["runId"] = "run-two"
    cycle("new run identity", 2300, ["EVENT run-long builder-343 21"])
    raw["threadsComplete"] = False
    raw["threads"][0]["runId"] = "run-three"
    cycle("partial thread source", 2300, [])
    raw["threadsComplete"] = True
    raw["threads"][0]["status"] = "waiting"
    cycle("waiting is not running", 2300, [])
    raw["threads"][0]["status"] = "running"
    raw["threads"][0]["startedAt"] = None
    cycle("unknown start", 2300, [])
    log.write_text("rate limit " + marker + "\nTraceback (most recent call last): " + marker + "\n")
    cycle("log alarms", 2300, ["EVENT rate-limit", "EVENT traceback runtime.log"])
    legacy = json.loads(state.read_text())
    legacy["logOffsets"][str(log)].pop("generation")
    state.write_text(json.dumps(legacy))
    cycle("legacy state restart log dedup", 2300, [])
    require(json.loads(state.read_text())["logOffsets"][str(log)]["generation"] == 0,
            "legacy state did not migrate to generation zero")
    with log.open("a") as stream:
        stream.write("rate-limit " + marker)
    cycle("partial line silent", 2300, [])
    with log.open("a") as stream:
        stream.write("\n")
    cycle("completed partial line", 2300, ["EVENT rate-limit"])
    log.rename(home / "runtime.log.1")
    log.write_text("Traceback (most recent call last): " + marker + "\nrate limit " + marker + "\n")
    cycle("replacement rotation", 2300, ["EVENT traceback runtime.log", "EVENT rate-limit"])
    cycle("rotation restart dedup", 2300, [])
    log.write_text("rate limit\n")
    cycle("copy truncate", 2300, ["EVENT rate-limit"])
    cycle("truncate restart dedup", 2300, [])

    with log.open("a") as stream:
        stream.write("ordinary padding before truncation\n")
    cycle("same-prefix before truncation", 2300, [])
    old_log_state = json.loads(state.read_text())["logOffsets"][str(log)]
    old_generation = old_log_state.get("generation", 0)
    log.write_text("rate limit\n")
    cycle("identical-line copy truncate", 2300, ["EVENT rate-limit"])
    new_log_state = json.loads(state.read_text())["logOffsets"][str(log)]
    require(new_log_state["identity"] == old_log_state["identity"], "copy truncation changed inode")
    require(new_log_state["generation"] == old_generation + 1, "truncation did not advance generation")
    cycle("identical-line truncation restart dedup", 2300, [])
    with log.open("a") as stream:
        stream.write("old padding\n")
    cycle("anchor before regrow", 2300, [])
    old_generation = json.loads(state.read_text())["logOffsets"][str(log)]["generation"]
    log.write_text("rate limit\nreplacement padding longer than previous log\n")
    cycle("anchor-detected truncate and regrow", 2300, ["EVENT rate-limit"])
    require(json.loads(state.read_text())["logOffsets"][str(log)]["generation"] == old_generation + 1,
            "anchor mismatch did not advance generation")
    cycle("anchor truncation restart dedup", 2300, [])

    spec = importlib.util.spec_from_file_location("installer", ROOT / "install_coordinator.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    require("coord-watch" in installer.BIN_FILES, "missing BIN_FILES mapping")
    mapping = [(src, target, mode) for src, target, mode in installer.plan(ROOT, home)
               if target == home / ".local/bin/coord-watch"]
    require(mapping == [(ROOT / "coordinator/bin/coord-watch", home / ".local/bin/coord-watch", 0o755)],
            "wrong executable mapping")
    installer.git_toplevel = lambda *_: None
    installer.retire_jobs = lambda *_: []
    installer.manual_monitors = lambda *_: []
    installer.reload_jobs = lambda *_: []
    original_run = subprocess.run
    def forbidden(*args, **kwargs):
        raise AssertionError("installer attempted a host subprocess")
    subprocess.run = forbidden
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            installer.install(ROOT, False, home=home, coordinator=home / "coordinator")
    finally:
        subprocess.run = original_run
    installed = home / ".local/bin/coord-watch"
    require(installed.read_bytes() == (ROOT / "coordinator/bin/coord-watch").read_bytes(),
            "installed source differs")
    require(stat.S_IMODE(installed.stat().st_mode) == 0o755 and os.access(installed, os.X_OK),
            "installed command is not executable 0755")
    receipt = json.loads((home / ".local/state/mac-ops/coordinator-installation.json").read_text())
    require(str(installed) in receipt["written"], "installation receipt omits executable")
    executable = installed
    cycle("installed executable restart dedup", 2300, [])
    with log.open("a") as stream:
        stream.write("rate limit installed command\n")
    cycle("installed executable new event", 2300, ["EVENT rate-limit"])
    cycle("installed executable event dedup", 2300, [])
    print("temporary HOME installation: PASS mapping, bytes, executable 0755, receipt, installed command")
    print("runtime write boundary: PASS only watch.json changed in every command invocation")
    print("synthetic private marker: PASS absent from stdout, stderr and persisted state")
    print("host boundaries: git_toplevel/retire_jobs/manual_monitors/reload_jobs replaced with inert fakes; subprocess forbidden during install")
    print("device, handset and live-service cases: WAIVED by Shyam 2026-11-14; not failed")
