#!/usr/bin/env python3
"""Proof for the ticket section matcher: three `ticket start --dry-run` runs.

Each case runs the real CLI in coordinator/bin/ticket. The GitHub read is
answered by the stub in tests/fixtures/ticket_start/ghstub, so no issue on
GitHub is read, written or changed.

Cases:
  comma   the skill's heading "Data, secrets and stop conditions" passes
  missing the same heading deleted still reports the section missing
  slash   the configured heading "Data/secrets and stop conditions" still passes
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "ticket_start"
REF = "shyamsivakumar/mac-ops#9001"

CASES = [
    ("comma", "checks passed"),
    ("missing", "refused: template sections Data/secrets and stop conditions (missing)"),
    ("slash", "checks passed"),
]


def run_case(case):
    """Run the CLI for one fixture case and return its command and output."""
    env = dict(os.environ)
    env["TICKET_STUB_FIXTURE"] = str(FIXTURES / case)
    env["TICKET_CACHE"] = tempfile.mkdtemp(prefix="ticket-section-proof-")
    env["PATH"] = str(FIXTURES / "ghstub") + os.pathsep + env["PATH"]
    command = [sys.executable, str(ROOT / "coordinator" / "bin" / "ticket"),
               "start", REF, "--dry-run"]
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                            text=True, timeout=300)
    return command, result


def main():
    failed = False
    for case, expected in CASES:
        command, result = run_case(case)
        output = (result.stdout + result.stderr).strip()
        print(f"$ {' '.join(command)}")
        print(f"# fixture: {case}")
        print(output)
        print(f"# exit: {result.returncode}")
        if expected not in output:
            failed = True
            print(f"# FAIL: expected {expected!r}")
        else:
            print("# PASS")
        print()
    if failed:
        print("ticket section proof: FAIL")
        return 1
    print("ticket section proof: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
