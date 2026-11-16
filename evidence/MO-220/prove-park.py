#!/usr/bin/env python3
"""Prove the parking lot and the snag log of the overnight shift (T10).

The proof runs the real `overnight park` command against temp records
folders, a stub `t3mcp` and the live board (read only). The stub serves
the threads it is given and refuses every call but a read, so an answer
would fail loudly instead of passing quietly.

What it proves:

1. a pending approval request is parked with its exact text, and the
   shift never answers it,
2. an old question that was already answered is not parked as if it
   waited for an answer,
3. a pending request whose text cannot be read still gets a parking
   entry, and the problem is logged,
4. a quoted request that holds markdown cannot break the morning
   report: the report still names one decision with its own default and
   its own recommendation,
5. a thread that cannot be read does not empty the parking lot: the
   decision that was waiting stays, and the failure is logged,
6. a problem that is still there is written once, not once a cycle,
7. a ticket the filter drops for an open question in the coordinator's
   decisions log is parked: it is a decision the shift cannot make.

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
FIXTURES = ROOT / "evidence" / "MO-220" / "fixtures"

STUB_T3MCP = '''#!/usr/bin/env python3
"""A stub t3mcp for the T10 proof.

It serves the thread it is asked for and refuses every other call,
because the shift must never answer an approval request. A thread in
the stub's `fail` list cannot be read, which is what a T3 failure looks
like from the shift's side."""
import json, os, sys
tool = sys.argv[2] if len(sys.argv) > 2 else ""
calls = os.environ.get("T3_CALLS", "")
with open(calls, "a") as stream:
    stream.write(tool + "\\n")
if tool != "t3_thread_read":
    print(f"stub t3mcp: refusing to {tool}: the shift never answers a request",
          file=sys.stderr)
    sys.exit(1)
payload = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
thread = payload.get("threadId") or ""
threads = json.load(open(os.environ["T3_THREADS"]))
if thread in threads.get("fail", []):
    print(f"stub t3mcp: the thread {thread} could not be read", file=sys.stderr)
    sys.exit(1)
print(json.dumps(threads.get(thread, {})))
'''

PROBLEMS = []


def check(condition, message):
    if not condition:
        PROBLEMS.append(message)
    return condition


def run(argv, env=None):
    result = subprocess.run(
        argv, capture_output=True, text=True, env=env, check=False
    )
    return result.returncode, result.stdout, result.stderr


def park_env(work, threads):
    bin_dir = work / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / "t3mcp"
    stub.write_text(STUB_T3MCP)
    stub.chmod(0o755)
    threads_file = work / "threads.json"
    threads_file.write_text(json.dumps(threads))
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    env["T3_THREADS"] = str(threads_file)
    env["T3_CALLS"] = str(work / "t3-calls.log")
    env["OVERNIGHT_T3MCP"] = str(stub)
    return env


def park(env, fixture, records, dry_run=False):
    argv = [
        sys.executable,
        str(OVERNIGHT),
        "park",
        "--fixture",
        str(fixture),
        "--root",
        str(records),
    ]
    if dry_run:
        argv.append("--dry-run")
    return run(argv, env=env)


def report(env, records):
    return run(
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


def decisions_of(out):
    """Return the report's "Decisions for you" section."""
    keep = False
    lines = []
    for line in out.splitlines():
        if line.startswith("## "):
            keep = "Decisions for you" in line
            if keep:
                lines.append(line)
            continue
        if keep:
            lines.append(line)
    return "\n".join(lines).strip()


def main() -> int:
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)

        # 1 and 2: a pending approval after an answered question.
        answered = FIXTURES / "answered-then-pending.json"
        threads = {
            "mcp:launch:t10-answered": json.loads(
                (FIXTURES / "threads-answered.json").read_text()
            ),
        }
        env = park_env(work, threads)
        records = work / "records-1"
        (records / "inbox").mkdir(parents=True)
        code, out, err = park(env, answered, records)
        check(code == 0, f"the park command exited {code}: {err.strip()}")
        lot = (records / "inbox" / "parking-lot.md").read_text()
        approval = "Approve running `python3 scripts/mac_ops_fast_check.py`?"
        old = "Should I widen the merge rule?"
        check(approval in lot, "the pending approval is not in the parking lot")
        check(old not in lot, "the answered question was parked as if it waited")
        check("- Default:" in lot, "the parking lot holds no default")
        check("- Recommend:" in lot, "the parking lot holds no recommendation")
        made = [
            line.strip()
            for line in (work / "t3-calls.log").read_text().splitlines()
            if line.strip()
        ]
        check(
            all(call == "t3_thread_read" for call in made),
            f"the shift called more than a read: {made}",
        )
        print("=== 1 and 2: the pending approval is parked, the answered question is not ===")
        print(lot.strip())

        # 4: a quoted request that holds markdown.
        markdown = FIXTURES / "markdown-request.json"
        threads = {
            "mcp:launch:t10-markdown": json.loads(
                (FIXTURES / "threads-markdown.json").read_text()
            )
        }
        env = park_env(work / "markdown", threads)
        records = work / "records-4"
        (records / "inbox").mkdir(parents=True)
        code, out, err = park(env, markdown, records)
        check(code == 0, f"the markdown park exited {code}: {err.strip()}")
        code, out, err = report(env, records)
        section = decisions_of(out)
        print("=== 4: the quoted markdown does not break the morning report ===")
        print(section)
        numbered = [
            line
            for line in section.splitlines()
            if line.strip()[:1].isdigit() and line.strip()[1:2] == "."
        ]
        check(
            len(numbered) == 1,
            f"the report does not name exactly one decision: {numbered}",
        )
        check(
            "the request stays unanswered" in section,
            "the report does not name the parked decision's own default",
        )
        check(
            "approve lines A-C" not in section,
            "the quoted request overrode the decision's own recommendation",
        )

        # 3 and 5: a request whose text cannot be read, and a thread that
        # cannot be read at all.
        unreadable = FIXTURES / "unreadable-request.json"
        threads = {
            "mcp:launch:t10-unreadable": json.loads(
                (FIXTURES / "threads-unreadable.json").read_text()
            ),
            "mcp:launch:t10-fails": {},
        }
        env = park_env(work / "unreadable", threads)
        records = work / "records-3"
        (records / "inbox").mkdir(parents=True)
        code, out, err = park(env, unreadable, records)
        lot = (records / "inbox" / "parking-lot.md").read_text()
        snag = (records / "inbox" / "snag-log.md").read_text()
        print("=== 3: a request whose text cannot be read is still parked ===")
        print(lot.strip())
        check("MO-221" in lot, "the unreadable request was not parked")
        check(
            "could not be read" in snag,
            "the unreadable request was not logged as a problem",
        )
        before = lot
        failing = FIXTURES / "failing-thread.json"
        threads["fail"] = ["mcp:launch:t10-fails"]
        env = park_env(work / "failing", threads)
        code, out, err = park(env, failing, records)
        after = (records / "inbox" / "parking-lot.md").read_text()
        snag = (records / "inbox" / "snag-log.md").read_text()
        print("=== 5: a thread that cannot be read does not empty the parking lot ===")
        check(
            before == after,
            "the parking lot was rewritten from an incomplete read",
        )
        check(code != 0, "the command reported success after a failed read")
        check(
            "was not rewritten" in snag,
            "the failed read was not logged as a problem",
        )

        # 6: a problem that is still there is written once.
        env = park_env(work / "again", threads)
        code, out, err = park(env, unreadable, records)
        snag = (records / "inbox" / "snag-log.md").read_text()
        print("=== 6: a problem that is still there is written once ===")
        check(
            snag.count("a thread waits on a person") == 1,
            "the same problem was written more than once",
        )

        # 7: a ticket the filter drops for an open question is parked.
        code, out, err = run(
            [sys.executable, str(OVERNIGHT), "board", "--json"], env=env
        )
        items = []
        if code == 0:
            try:
                items = json.loads(out).get("items") or []
            except ValueError:
                items = []
        if items:
            item = items[0]
            key = item.get("key") or ""
            number = item.get("number")
            decisions = work / "decisions.md"
            decisions.write_text(
                f"OPEN (needs answer): {key} #{number} — which shape should this take?\n"
            )
            env = dict(env)
            env["OVERNIGHT_DECISIONS"] = str(decisions)
            records = work / "records-7"
            (records / "inbox").mkdir(parents=True)
            code, out, err = run(
                [
                    sys.executable,
                    str(OVERNIGHT),
                    "park",
                    "--root",
                    str(records),
                    "--dry-run",
                ],
                env=env,
            )
            print("=== 7: the ticket with an open question is parked ===")
            print(out.strip()[:2000])
            check(
                "which shape should this take?" in out,
                "the open question was not parked",
            )
            check(
                "Default:" in out and "Recommend:" in out,
                "the parked decision holds no default or recommendation",
            )
        else:
            print("=== 7: skipped, the board shows no item to park ===")

    if PROBLEMS:
        print("FAIL:")
        for problem in PROBLEMS:
            print(f"  - {problem}")
        return 1
    print("PASS: the request is parked with its exact text and never answered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
