#!/usr/bin/env python3
"""Walk one real path end to end and answer pass or fail.

Three steps run the real code against fixtures and temp state:
  tick   `coordq gatekeep --dry-run` on a temp queue; the queue must not change
  gate   the overnight gate reader on a recorded real gate reply
  card   `ticket start --dry-run --print-brief` on a fixture issue

Every step writes its command, output and exit code to a log in the output
directory. The last line names each failed step, and the exit code is 0 or 1.
"""
import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "walk"
TICKET_FIXTURE = ROOT / "tests" / "fixtures" / "ticket_start" / "comma"
GATE_HEAD = "2d68d1404810f937640b6b475f4b1b606761b007"
READ_GATE = (
    "import sys, importlib.machinery as m, importlib.util as u\n"
    "loader = m.SourceFileLoader('overnight_walk', sys.argv[1])\n"
    "module = u.module_from_spec(u.spec_from_loader('overnight_walk', loader))\n"
    "loader.exec_module(module)\n"
    "verdict = module.read_gate_report('walk-thread', 30.0, sys.argv[2])[0]\n"
    "print('verdict=' + verdict)\n"
)
FAKE_T3MCP = '#!/bin/sh\nexec cat "$WALK_GATE_FIXTURE"\n'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def queue_untouched(path, expected):
    try:
        return isinstance(json.loads(path.read_text()), dict) and sha(path) == expected
    except ValueError:
        return False


def run_step(name, command, env, timeout, log_dir):
    started = time.time()
    process = subprocess.Popen(command, env=env, cwd=ROOT, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        output, _ = process.communicate(timeout=timeout)
        ok, reason = process.returncode == 0, f"exit {process.returncode}"
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        output, _ = process.communicate()
        ok, reason = False, f"hung past {timeout}s"
    (log_dir / f"{name}.log").write_text(
        f"$ {' '.join(command)}\n{output}\n# {reason} in {time.time() - started:.1f}s\n")
    return ok, reason, output


def walk(args, out):
    sys.path.insert(0, str(ROOT / "coordinator" / "bin"))
    import gh_isolation

    work = out / "state"
    queue_dir, journal_dir, bin_dir, card_queue = (work / n for n in ("queue", "journal", "bin", "card-queue"))
    for folder in (queue_dir, journal_dir, bin_dir, card_queue):
        folder.mkdir(parents=True)
    env = gh_isolation.environment({
        "PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", ""),
        "COORDQ_DIR": str(queue_dir), "COORD_JOURNAL_DIR": str(journal_dir),
        "COORDINATOR_TEST_ISOLATION_DIR": str(work / "isolation")})
    results = []

    def step(name, prepare, command, step_env, check):
        try:
            prepare()
        except OSError as error:
            results.append((name, False, f"fixture unreadable: {error}"))
            (out / f"{name}.log").write_text(f"fixture unreadable: {error}\n")
            return
        ok, reason, output = run_step(name, command, step_env, args.step_timeout, out)
        results.append((name, ok and check(output), reason if not ok else "result check failed"))

    queue_file, config, before = queue_dir / "queue.json", work / "tickets.json", {}

    def prepare_tick():
        shutil.copy(args.queue_fixture, queue_file)
        shutil.copy(FIXTURES / "tickets.json", config)
        (queue_dir / "gh-login").write_text("walk-check\n")
        before["sha"] = sha(queue_file)

    step("tick", prepare_tick,
         [sys.executable, str(ROOT / "coordinator/bin/coordq"), "gatekeep", "--dry-run", "--config", str(config)],
         env, lambda _: queue_untouched(queue_file, before["sha"]))

    fake = bin_dir / "t3mcp"

    def prepare_gate():
        fake.write_text(FAKE_T3MCP)
        fake.chmod(0o755)
        Path(args.gate_fixture).read_bytes()

    step("gate", prepare_gate,
         [sys.executable, "-c", READ_GATE, str(ROOT / "coordinator/overnight/overnight"), GATE_HEAD],
         {**env, "OVERNIGHT_T3MCP": str(fake), "WALK_GATE_FIXTURE": str(args.gate_fixture)},
         lambda output: "verdict=PASS" in output)

    ghstub = ROOT / "tests" / "fixtures" / "ticket_start" / "ghstub"
    step("card", lambda: (TICKET_FIXTURE / "body.md").read_bytes(),
         [sys.executable, str(ROOT / "coordinator/bin/ticket"), "start", "shyamsivakumar/mac-ops#9001",
          "--dry-run", "--print-brief"],
         {**env, "TICKET_STUB_FIXTURE": str(TICKET_FIXTURE), "TICKET_CACHE": str(work / "ticket-cache"),
          "COORDQ_DIR": str(card_queue), "PATH": str(ghstub) + os.pathsep + env["PATH"]},
         lambda output: "checks passed" in output)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", help="directory for the step logs (default: a new temp directory)")
    parser.add_argument("--step-timeout", type=float, default=120)
    parser.add_argument("--gate-fixture", default=str(FIXTURES / "gate-reply.json"))
    parser.add_argument("--queue-fixture", default=str(FIXTURES / "queue.json"))
    args = parser.parse_args()
    out = Path(args.out or tempfile.mkdtemp(prefix="walk-check-"))
    out.mkdir(parents=True, exist_ok=True)
    results = walk(args, out)
    failed = [f"{name} ({reason})" for name, ok, reason in results if not ok]
    (out / "summary.json").write_text(json.dumps(
        [{"step": name, "ok": ok, "reason": reason} for name, ok, reason in results], indent=1) + "\n")
    if failed:
        print(f"walk FAIL step {'; '.join(failed)}; logs {out}")
        return 1
    print(f"walk PASS {len(results)} steps ({', '.join(name for name, _, _ in results)}); logs {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
