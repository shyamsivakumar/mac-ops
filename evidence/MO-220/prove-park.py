#!/usr/bin/env python3
"""Prove that the shift parks a pending approval request and never answers it.

The proof runs the real `overnight park` command against a temp records
folder and a stub `t3mcp`. The stub serves one thread that waits on a
person: the thread holds a pending request with its exact text.

The stub refuses every call but `t3_thread_read` and writes the name of
every other call to a log, so an answer would fail loudly instead of
passing quietly. The proof then shows:

1. the parking lot holds the request, quoted exactly as the tool showed it,
   with a default and a recommendation,
2. the stub was never asked to do anything but read, so the shift never
   answered the request,
3. the morning report reads the parking lot and names the decision for
   Shyam, with the recommendation and the default.

Run it from the mac-ops checkout:

    python3 evidence/MO-220/prove-park.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OVERNIGHT = ROOT / "coordinator" / "overnight" / "overnight"
FIXTURE = ROOT / "evidence" / "MO-220" / "fixture-pending-approval.json"

STUB_T3MCP = '''#!/usr/bin/env python3
"""A stub t3mcp for the T10 proof.

It serves the fixture's thread for a read and refuses every other call,
because the shift must never answer an approval request."""
import json, os, sys
tool = sys.argv[2] if len(sys.argv) > 2 else ""
calls = os.environ.get("T3_CALLS", "")
if tool != "t3_thread_read":
    with open(calls, "a") as stream:
        stream.write(tool + "\\n")
    print(f"stub t3mcp: refusing to {tool}: the shift never answers a request",
          file=sys.stderr)
    sys.exit(1)
fixture = json.load(open(os.environ["T3_FIXTURE"]))
with open(calls, "a") as stream:
    stream.write(tool + "\\n")
print(json.dumps(fixture["response"]))
'''


def run(argv, env=None, cwd=None):
    result = subprocess.run(
        argv, capture_output=True, text=True, env=env, cwd=cwd, check=False
    )
    return result.returncode, result.stdout, result.stderr


def main() -> int:
    fixture = json.loads(FIXTURE.read_text())
    request_text = ""
    for item in fixture["response"]["items"]:
        if item.get("type") == "question":
            request_text = item.get("text") or ""
    if not request_text:
        print("the fixture holds no pending request")
        return 1

    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        bin_dir = work / "bin"
        bin_dir.mkdir()
        stub = bin_dir / "t3mcp"
        stub.write_text(STUB_T3MCP)
        stub.chmod(0o755)
        calls = work / "t3-calls.log"
        records = work / "records"
        (records / "inbox").mkdir(parents=True)
        env = dict(os.environ)
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["T3_FIXTURE"] = str(FIXTURE)
        env["T3_CALLS"] = str(calls)
        env["OVERNIGHT_T3MCP"] = str(stub)

        print("=== overnight park --fixture (the real command) ===")
        code, out, err = run(
            [
                sys.executable,
                str(OVERNIGHT),
                "park",
                "--fixture",
                str(FIXTURE),
                "--root",
                str(records),
            ],
            env=env,
        )
        print(out, end="")
        if err:
            print(err, end="", file=sys.stderr)
        if code != 0:
            print(f"FAIL: the command exited {code}")
            return 1

        parking = (records / "inbox" / "parking-lot.md").read_text()
        print("=== inbox/parking-lot.md ===")
        print(parking, end="")

        problems = []
        if request_text not in parking:
            problems.append("the parking lot does not hold the exact request text")
        if "- Default:" not in parking:
            problems.append("the parking lot holds no default")
        if "- Recommend:" not in parking:
            problems.append("the parking lot holds no recommendation")
        made = [line.strip() for line in calls.read_text().splitlines() if line.strip()]
        if any(call != "t3_thread_read" for call in made):
            problems.append(f"the shift called more than a read: {made}")
        if not made:
            problems.append("the stub was never called, so nothing was read")

        print("=== the calls the shift made ===")
        print("\n".join(made) if made else "(none)")
        print("=== overnight report --dry-run (the decision reaches Shyam) ===")
        code, out, err = run(
            [
                sys.executable,
                str(OVERNIGHT),
                "report",
                "--root",
                str(records),
                "--dry-run",
            ],
            env=env,
        )
        if code != 0:
            problems.append(f"the report exited {code}")
        decisions = []
        keep = False
        for line in out.splitlines():
            if line.startswith("## "):
                keep = "Decisions for you" in line
                if keep:
                    decisions.append(line)
                continue
            if keep:
                decisions.append(line)
        print("\n".join(decisions).strip() or "(the report named no decision)")
        if "Recommend:" not in "\n".join(decisions):
            problems.append("the report does not name the parked decision")

        if problems:
            print("FAIL:")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        print("PASS: the request was parked with its exact text and never answered")
        return 0


if __name__ == "__main__":
    sys.exit(main())
