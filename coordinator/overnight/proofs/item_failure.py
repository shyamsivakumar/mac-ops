"""Run the lane driver offline with executable command fixtures."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SOURCE = Path(__file__).resolve().parents[1] / "lane_driver.py"
REPOS = ["shyamsivakumar/mac-ops", "shyamsivakumar/strategy-replay-workbench",
         "shyamsivakumar/fantasy-football-toolkit", "shyamsivakumar/catalouge"]


def main():
    with tempfile.TemporaryDirectory(prefix="lane-item-proof-") as directory:
        root = Path(directory)
        home = root / "home"
        commands = root / "bin"
        commands.mkdir()
        coordinator = home / "Code/coordinator"
        (coordinator / "loop").mkdir(parents=True)
        (coordinator / "queue").mkdir()
        (home / ".coordinator").mkdir()
        (home / ".coordinator/tickets.json").write_text(json.dumps({
            "repos": {repo: {"key": str(i), "projectId": repo}
                      for i, repo in enumerate(REPOS)}}))
        (coordinator / "decisions.json").write_text('{"items":[]}')
        (coordinator / "queue/dispatch-receipts.json").write_text("{}")
        executable = r"""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["PROOF_COMMAND_LOG"], "a") as log:
    log.write(json.dumps([name] + args) + "\n")
if name == "gh" and args == ["api", "rate_limit"]:
    print(json.dumps({"resources": {k: {"remaining": 9000} for k in ("core", "graphql")}}))
elif name == "gh" and args[:2] == ["pr", "list"]:
    repo = args[args.index("-R") + 1]
    numbers = [90001, 90002] if repo.endswith("/mac-ops") else [90003]
    print(json.dumps([{"number": n, "state": "OPEN", "isDraft": False,
                      "headRefOid": "a" * 40, "body": "Builder check: PASS " + "a" * 40,
                      "mergeable": "MERGEABLE"} for n in numbers]))
elif name == "gh" and args[:2] == ["issue", "list"]:
    print("[]")
elif name == "ticket" and args[:1] == ["list"]:
    print('{"issues":[]}')
elif name == "ticket" and args[:1] == ["gate"]:
    if args[1].endswith("#90001") or os.environ.get("PROOF_ALL_FAIL") == "1":
        print("planted gate refusal")
        sys.exit(2)
    print("offline gate brief " + "a" * 40)
elif name == "t3mcp":
    print('{"threads":[]}')
else:
    sys.exit("unexpected command: " + repr([name] + args))
"""
        for name in ("gh", "ticket", "t3mcp"):
            path = commands / name
            path.write_text(executable)
            path.chmod(0o755)
        # Relocate hardcoded filesystem paths only; retain every driver function.
        driver = root / "driver.py"
        driver.write_text(SOURCE.read_text().replace("/Users/shyamsivakumar", str(home))
                          + "\nDRY = True\nmain()\n")
        log = root / "commands.jsonl"
        env = dict(os.environ, PATH=str(commands) + os.pathsep + os.environ["PATH"],
                   PROOF_COMMAND_LOG=str(log))
        for all_fail in (False, True):
            log.write_text("")
            result = subprocess.run([sys.executable, str(driver)], env=dict(
                env, PROOF_ALL_FAIL="1" if all_fail else "0"),
                capture_output=True, text=True, timeout=60)
            print("CASE", "all items fail" if all_fail else "one item fails")
            print(result.stdout, end="")
            assert result.returncode != 0, result.stderr
            expected = 5 if all_fail else 1
            assert f"lane pass completed with {expected} item failures" in result.stderr
            errors = [line for line in result.stdout.splitlines() if line.startswith("ITEM ERROR")]
            assert len(errors) == expected, (len(errors), result.stdout, result.stderr)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            gates = [call[2] for call in calls if call[:2] == ["ticket", "gate"]]
            assert gates.index(REPOS[0] + "#90001") < gates.index(REPOS[0] + "#90002")
            assert REPOS[-1] + "#90003" in gates
            assert "Concerning" not in log.read_text()
            assert "ITEM SUMMARY failures=" + str(expected) in result.stdout
            assert not (coordinator / "loop/lanes-ledger.json").exists()
            print("PASS: later items and lanes processed; nonzero health; Concerning untouched")
    print("PASS: temporary plant and sandbox removed")


if __name__ == "__main__":
    main()
