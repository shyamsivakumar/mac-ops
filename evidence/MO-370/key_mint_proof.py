#!/usr/bin/env python3
"""Proof for MO-370: the ticket CLI mints the key when it opens a ticket.

The run is hermetic. A fake `gh` on PATH answers the issue list and records
the issue create, so nothing touches GitHub.

    python3 evidence/MO-370/key_mint_proof.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TICKET = ROOT / "coordinator" / "bin" / "ticket"

FAKE_GH = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
log = os.environ["FAKE_GH_LOG"]
if args[:2] == ["issue", "list"]:
    print(json.dumps(json.load(open(os.environ["FAKE_GH_ISSUES"]))))
elif args[:2] == ["issue", "create"]:
    with open(log, "a") as handle:
        handle.write(json.dumps(args) + "\\n")
    print("https://github.com/fixture/repo/issues/999")
else:
    sys.stderr.write("unexpected gh call: " + " ".join(args) + "\\n")
    sys.exit(1)
"""


def run_ticket(env, args):
    result = subprocess.run([sys.executable, str(TICKET)] + args, capture_output=True, text=True, env=env)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def main():
    failures = []
    with tempfile.TemporaryDirectory(prefix="mo-370-proof-") as tmp:
        tmp = Path(tmp)
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "gh"
        fake.write_text(FAKE_GH)
        fake.chmod(0o755)
        log = tmp / "gh.log"
        issues = tmp / "issues.json"
        issues.write_text(json.dumps([
            {"number": 41, "title": "MO-1016 · the last keyed ticket"},
            {"number": 42, "title": "a ticket with no key at all"},
            {"number": 43, "title": "MO-1017 · a key that is already taken"},
        ]))
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
               "FAKE_GH_LOG": str(log), "FAKE_GH_ISSUES": str(issues),
               "TICKET_CACHE": str(tmp / "cache")}

        # 1. A keyless title is keyed with the next free key.
        code, out, err = run_ticket(env, ["open", "--repo", "shyamsivakumar/mac-ops",
                                          "--title", "Prove that a keyless title is keyed", "--dry-run"])
        plan = json.loads(out) if out else {}
        ok = code == 0 and plan.get("title") == "MO-1018 · Prove that a keyless title is keyed"
        print(f"[{'PASS' if ok else 'FAIL'}] keyless title dry run -> {out or err}")
        if not ok:
            failures.append("keyless title dry run")

        # 2. A keyed title passes as it is, and nothing is opened in a dry run.
        code, out, err = run_ticket(env, ["open", "--repo", "shyamsivakumar/mac-ops",
                                          "--title", "MO-1020 · a title that brings its own key", "--dry-run"])
        plan = json.loads(out) if out else {}
        ok = code == 0 and plan.get("key") == "MO-1020" and plan.get("title") == "MO-1020 · a title that brings its own key"
        print(f"[{'PASS' if ok else 'FAIL'}] keyed title dry run -> {out or err}")
        if not ok:
            failures.append("keyed title dry run")

        # 3. A key that is already taken is refused.
        code, out, err = run_ticket(env, ["open", "--repo", "shyamsivakumar/mac-ops",
                                          "--title", "MO-1017 · a key that is already taken", "--dry-run"])
        ok = code == 2 and "already used by issue #43" in err
        print(f"[{'PASS' if ok else 'FAIL'}] taken key refused -> {err or out}")
        if not ok:
            failures.append("taken key refused")

        # 4. A key from another repo is refused.
        code, out, err = run_ticket(env, ["open", "--repo", "shyamsivakumar/mac-ops",
                                          "--title", "SRW-900 · the wrong repo's key", "--dry-run"])
        ok = code == 2 and "does not match repo key MO" in err
        print(f"[{'PASS' if ok else 'FAIL'}] wrong key prefix refused -> {err or out}")
        if not ok:
            failures.append("wrong key prefix refused")

        # 5. --require-key refuses a keyless title with a clear message.
        code, out, err = run_ticket(env, ["open", "--repo", "shyamsivakumar/mac-ops",
                                          "--title", "A title with no key", "--require-key", "--dry-run"])
        ok = code == 2 and "missing key in title" in err
        print(f"[{'PASS' if ok else 'FAIL'}] require-key refused -> {err or out}")
        if not ok:
            failures.append("require-key refused")

        # 6. The real create writes the minted title.
        code, out, err = run_ticket(env, ["open", "--repo", "shyamsivakumar/mac-ops",
                                          "--title", "Prove that a keyless title is keyed",
                                          "--label", "stage:todo,type:chore,priority:3"])
        created = log.read_text().strip().splitlines() if log.exists() else []
        args = json.loads(created[-1]) if created else []
        ok = (code == 0 and args[:4] == ["issue", "create", "-R", "shyamsivakumar/mac-ops"]
              and "MO-1018 · Prove that a keyless title is keyed" in args
              and "stage:todo,type:chore,priority:3" in args)
        print(f"[{'PASS' if ok else 'FAIL'}] create wrote the minted title -> {created[-1] if created else err}")
        if not ok:
            failures.append("create wrote the minted title")

        # 7. A repo that is not in tickets.json is refused.
        code, out, err = run_ticket(env, ["open", "--repo", "someone/else", "--title", "No key here", "--dry-run"])
        ok = code == 2 and "not configured in tickets.json" in err
        print(f"[{'PASS' if ok else 'FAIL'}] unknown repo refused -> {err or out}")
        if not ok:
            failures.append("unknown repo refused")

    print("MO-370 key mint proof:", "passed" if not failures else f"failed: {', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
