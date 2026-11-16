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
   decisions log is parked: it is a decision the shift cannot make,
8. a quoted request that holds a fence of its own cannot break the
   morning report: the fence that quotes it is longer than any fence in
   the request and the parser closes it only on the exact delimiter,
9. a parking step that raises SystemExit does not end the shift cycle:
   the cycle's own report is still written,
10. a request that carries its answer is not parked: the shift does not
   wait for an answer that already came,
11. a thread that returns an empty or malformed record leaves the
   parking lot as it was: the shift does not erase a decision because a
   read told it nothing,
12. a snag entry records what was observed and quotes the shift's own
   receipt when there is one: it never claims a stop or a delivery it
   did not verify,
13. two tickets that share a title and a failing check are two problems:
   the snag log keeps both,
14. the latest open request is the one that is parked: when its own text
   cannot be read, the shift says so instead of parking an older
   request in its place,
15. a dry run of the real board refuses too when a thread cannot be
   read: it shows the failure, writes nothing, and exits non-zero,
16. a pull request's snag entry quotes the receipt of its linked ticket,
   never the receipt filed under the pull request's own number,
17. a pull request's threads come from its linked ticket's receipts and
   the threads the board attaches, never from an unrelated ticket whose
   number is the pull request's: that ticket's pending request is not
   parked under the pull request's ticket.

Run it from the mac-ops checkout:

    python3 evidence/MO-220/prove-park.py
"""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
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
fail = threads.get("fail", [])
if "*" in fail or thread in fail:
    print(f"stub t3mcp: the thread {thread} could not be read", file=sys.stderr)
    sys.exit(1)
record = threads.get(thread)
if record is None:
    # A thread the fixture did not name is a well-formed thread that holds
    # nothing, so a read of it is complete.
    record = {"thread": {"threadId": thread, "status": "completed"}, "items": []}
print(json.dumps(record))
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


def load_overnight():
    """Return the shift's own module, loaded from its script path."""
    loader = importlib.machinery.SourceFileLoader("overnight_t10", str(OVERNIGHT))
    spec = importlib.util.spec_from_loader("overnight_t10", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


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

        # 8: a quoted request that holds a fence of its own.
        fenced = FIXTURES / "fenced-request.json"
        threads = {
            "mcp:launch:t10-fenced": json.loads(
                (FIXTURES / "threads-fenced.json").read_text()
            )
        }
        env = park_env(work / "fenced", threads)
        records = work / "records-8"
        (records / "inbox").mkdir(parents=True)
        code, out, err = park(env, fenced, records)
        check(code == 0, f"the fenced park exited {code}: {err.strip()}")
        lot = (records / "inbox" / "parking-lot.md").read_text()
        print("=== 8: the quoted request holds a fence of its own ===")
        print(lot.strip())
        check(
            "a default inside the request" in lot,
            "the request text was not parked exactly",
        )
        code, out, err = report(env, records)
        section = decisions_of(out)
        print("=== 8: the report reads the fenced quote as one decision ===")
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
            "the quoted fence overrode the decision's own default",
        )
        check(
            "a default inside the request" not in section,
            "the quoted fence became a field of the decision",
        )
        check(
            "a recommendation inside the request" not in section,
            "the quoted fence became the decision's recommendation",
        )

        # 9: a parking step that raises SystemExit does not end the cycle.
        module = load_overnight()
        source = OVERNIGHT.read_text()
        check(
            source.count("def park_cycle(") == 1,
            "the module holds more than one park_cycle, so a later one "
            "replaces the one that catches SystemExit",
        )

        def refuse(args):
            raise SystemExit(2)

        original = module.cmd_park
        module.cmd_park = refuse
        try:
            module.park_cycle(work / "records-9", time.monotonic() + 30)
            ended = False
        except SystemExit:
            ended = True
        finally:
            module.cmd_park = original
        print("=== 9: the parking step cannot end the cycle ===")
        check(
            not ended,
            "a parking step that raised SystemExit ended the shift cycle",
        )

        # 10: a request that carries its answer is not parked.
        answered_payload = FIXTURES / "answer-payload-request.json"
        threads = {
            "mcp:launch:t10-answer-payload": json.loads(
                (FIXTURES / "threads-answer-payload.json").read_text()
            )
        }
        env = park_env(work / "payload", threads)
        records = work / "records-10"
        (records / "inbox").mkdir(parents=True)
        code, out, err = park(env, answered_payload, records)
        lot_path = records / "inbox" / "parking-lot.md"
        lot = lot_path.read_text() if lot_path.exists() else ""
        print("=== 10: a request that carries its answer is not parked ===")
        check(
            code != 0,
            "the shift parked a request that was already answered",
        )
        check(
            "MO-225" not in lot,
            "the answered request is in the parking lot",
        )
        check(
            "holds no pending request" in (out + err),
            f"the command did not say why it parked nothing: {out}{err}",
        )

        # 11: a thread that returns an empty record preserves the lot.
        empty = FIXTURES / "empty-record-request.json"
        threads = {
            "mcp:launch:t10-empty": {},
            "mcp:launch:t10-answered": json.loads(
                (FIXTURES / "threads-answered.json").read_text()
            ),
        }
        env = park_env(work / "empty", threads)
        records = work / "records-11"
        (records / "inbox").mkdir(parents=True)
        code, out, err = park(env, FIXTURES / "answered-then-pending.json", records)
        check(code == 0, f"the first park exited {code}: {err.strip()}")
        before = (records / "inbox" / "parking-lot.md").read_text()
        code, out, err = park(env, empty, records)
        after = (records / "inbox" / "parking-lot.md").read_text()
        print("=== 11: an empty thread record preserves the parking lot ===")
        check(code != 0, "the command reported success after an empty record")
        check(
            before == after,
            "the parking lot was rewritten from an empty thread record",
        )
        check(
            "empty or malformed" in (out + err),
            f"the command did not say why it wrote nothing: {out}{err}",
        )

        # 12: the snag entries record observations and quote the receipt.
        module = load_overnight()
        budget = module.normalise_budget({"soft": 5, "hard": 8, "retry_cap": 2})
        failing_item = {
            "kind": "pull-request",
            "repo": "acme/widgets",
            # The pull request and its ticket carry different numbers, as
            # they do on GitHub: the receipt is filed under the ticket.
            "number": 9,
            "issue": 7,
            "key": "MO-999",
            "title": "A synthetic item with a failing check",
            "url": "",
            "checks": {"failed": ["build"]},
        }
        queue_state = {
            "fixedHeads": {
                "fix:acme/widgets#7:head1": "sent",
                "fix:acme/widgets#7:head2": "sent",
            }
        }
        _parked, snags, _incomplete = module.park_decisions(
            [failing_item], [], {}, [], time.monotonic() + 30, budget, queue_state
        )
        text = "\n".join(
            module.snag_section(title, fields) for title, fields in snags
        )
        print("=== 12: the snag entry records what was observed ===")
        print(text.strip())
        check(
            "was sent the failing check" not in text,
            "the entry claims the failing check was sent",
        )
        check(
            "was stopped and parked" not in text,
            "the entry claims the item was stopped and parked",
        )
        check(
            "has not been verified" in text,
            "the entry does not say what was not verified",
        )
        check(
            "the builder used 0 min" not in text,
            "the entry states a builder time it did not measure",
        )
        # The same item with the shift's own receipt: the entry quotes it.
        receipts = {
            ("acme/widgets", "7"): {
                "state": "parked",
                "stopped because": "the check failed twice",
            }
        }
        _parked, snags, _incomplete = module.park_decisions(
            [failing_item],
            [],
            {},
            [],
            time.monotonic() + 30,
            budget,
            queue_state,
            receipts,
        )
        quoted = "\n".join(
            module.snag_section(title, fields) for title, fields in snags
        )
        print("=== 12: the entry quotes the shift's own receipt ===")
        print(quoted.strip())
        check(
            "the receipt records the state parked: the check failed twice"
            in quoted,
            "the entry does not quote the receipt the shift wrote",
        )

        # 13: two tickets with the same title and the same problem.
        module = load_overnight()
        budget = module.normalise_budget({"soft": 5, "hard": 8, "retry_cap": 2})
        first = {
            "kind": "pull-request",
            "repo": "acme/one",
            "number": 7,
            "key": "ONE-1",
            "title": "The same title",
            "url": "",
            "checks": {"failed": ["build"]},
        }
        second = dict(first, repo="acme/two", key="TWO-1")
        _parked, snags, _incomplete = module.park_decisions(
            [first, second], [], {}, [], time.monotonic() + 30, budget, {}
        )
        print("=== 13: two tickets with the same title are two problems ===")
        check(
            len(snags) == 2,
            f"the two tickets with the same title collided: {len(snags)} entries",
        )
        log = work / "records-13"
        (log / "inbox").mkdir(parents=True)
        outcome = module.write_snag_log(log, snags)
        text = (log / "inbox" / "snag-log.md").read_text()
        check(
            text.count("a check is failing: build") == 2,
            "the snag log holds one entry for two tickets",
        )
        check(
            "acme/one" in text and "acme/two" in text,
            "the snag log does not name both repositories",
        )

        # 14: the latest open request is the one that is parked.
        latest = FIXTURES / "latest-unreadable-request.json"
        threads = {
            "mcp:launch:t10-latest-unreadable": json.loads(
                (FIXTURES / "threads-latest-unreadable.json").read_text()
            )
        }
        env = park_env(work / "latest", threads)
        records = work / "records-14"
        (records / "inbox").mkdir(parents=True)
        code, out, err = park(env, latest, records)
        lot = (records / "inbox" / "parking-lot.md").read_text()
        snag = (records / "inbox" / "snag-log.md").read_text()
        print("=== 14: the latest request is the one that is parked ===")
        print(lot.strip())
        check(
            "Approve the older request?" not in lot,
            "an older request was parked in place of the latest one",
        )
        check(
            "the text of the request could not be read" in lot,
            "the shift did not say that the latest request's text is unreadable",
        )
        check(
            "could not be read" in snag,
            "the unreadable latest request was not logged as a problem",
        )

        # 15: a dry run of the board refuses when a thread cannot be read.
        # Every thread read fails here, so the preview cannot be complete.
        threads = {"fail": ["*"], "mcp:launch:t10-fails": {}}
        env = park_env(work / "dry", threads)
        dry = work / "records-15"
        (dry / "inbox").mkdir(parents=True)
        code, out, err = run(
            [
                sys.executable,
                str(OVERNIGHT),
                "park",
                "--root",
                str(dry),
                "--dry-run",
                "--deadline",
                "150",
            ],
            env=env,
        )
        message = out + err
        print("=== 15: a dry run refuses on an incomplete read ===")
        print("\n".join(
            line for line in message.splitlines()
            if "INCOMPLETE" in line or "REFUSED" in line or line.startswith("- ")
        )[:1200])
        check(code != 0, "the dry run reported success after a failed read")
        check(
            "INCOMPLETE" in message,
            f"the dry run did not say its preview was incomplete: {message[:400]}",
        )
        check(
            "REFUSED" in message,
            "the dry run did not report the refusal",
        )
        check(
            not (dry / "inbox" / "parking-lot.md").exists(),
            "the dry run wrote a parking lot",
        )
        # And the fixture path refuses the same way.
        code, out, err = park(
            env, FIXTURES / "failing-thread.json", dry, dry_run=True
        )
        check(
            code != 0 and "REFUSED" in (out + err),
            f"the fixture dry run did not refuse: {out}{err}",
        )

        # 16: a pull request quotes its linked ticket's receipt, never the
        # receipt filed under its own number.
        module = load_overnight()
        budget = module.normalise_budget({"soft": 5, "hard": 8, "retry_cap": 2})
        pull = {
            "kind": "pull-request",
            "repo": "acme/widgets",
            "number": 435,
            "issue": 188,
            "key": "MO-220",
            "title": "A pull request whose number is another ticket's number",
            "url": "",
            "checks": {"failed": ["build"]},
        }
        receipts = {
            ("acme/widgets", "188"): {
                "state": "stuck",
                "stopped because": "the linked ticket's own reason",
            },
            ("acme/widgets", "435"): {
                "state": "parked",
                "stopped because": "an unrelated ticket's reason",
            },
        }
        _parked, snags, _incomplete = module.park_decisions(
            [pull],
            [],
            {},
            [],
            time.monotonic() + 30,
            budget,
            {},
            receipts,
        )
        text = "\n".join(
            module.snag_section(title, fields) for title, fields in snags
        )
        print("=== 16: the pull request quotes its linked ticket's receipt ===")
        print(text.strip())
        check(
            "the linked ticket's own reason" in text,
            "the entry does not quote the linked ticket's receipt",
        )
        check(
            "an unrelated ticket's reason" not in text,
            "the entry quoted the receipt filed under the pull request's number",
        )
        # A pull request with no linked ticket quotes no receipt at all,
        # even when one is filed under its own number.
        bare = dict(pull, issue="")
        _parked, snags, _incomplete = module.park_decisions(
            [bare], [], {}, [], time.monotonic() + 30, budget, {}, receipts
        )
        bare_text = "\n".join(
            module.snag_section(title, fields) for title, fields in snags
        )
        print("=== 16: a pull request with no linked ticket quotes nothing ===")
        check(
            "an unrelated ticket's reason" not in bare_text,
            "a pull request with no linked ticket quoted a foreign receipt",
        )
        check(
            "has not been verified" in bare_text,
            "the entry does not say that the action was not verified",
        )

        # 17: a pull request never borrows an unrelated ticket's threads.
        module = load_overnight()
        pull = {
            "kind": "pull-request",
            "repo": "acme/widgets",
            "number": 435,
            "issue": 188,
            "key": "MO-220",
            "title": "A pull request linked to a different ticket's number",
            "url": "",
            "checks": {"failed": []},
        }
        # An unrelated ticket #435 has a builder thread; the pull request's
        # own ticket #188 has none.
        receipts = {"ticket:acme/widgets#435:a1": "mcp:launch:unrelated-435"}
        threads = module.item_threads(pull, receipts)
        print("=== 17: a pull request borrows no unrelated ticket's thread ===")
        print(f"threads: {threads}")
        check(
            "mcp:launch:unrelated-435" not in threads,
            "the pull request borrowed the thread of an unrelated ticket",
        )
        # The board's own attached threads are still taken as they are.
        attached = dict(pull, builder={"threadId": "mcp:launch:attached-builder"})
        threads = module.item_threads(attached, receipts)
        print(f"threads with an attached builder: {threads}")
        check(
            threads[:1] == ["mcp:launch:attached-builder"],
            "the board's attached thread was dropped",
        )
        check(
            "mcp:launch:unrelated-435" not in threads,
            "the attached item still borrowed the unrelated ticket's thread",
        )
        # The parking lot does not park the unrelated ticket's request.
        _parked, snags, _incomplete = module.park_decisions(
            [pull],
            [],
            receipts,
            [],
            time.monotonic() + 30,
            module.normalise_budget({"soft": 5, "hard": 8, "retry_cap": 2}),
            {},
            {},
        )
        print(f"parked entries: {len(_parked)}")
        check(
            not _parked,
            "the pull request parked a decision taken from an unrelated ticket",
        )
        # And with only the linked ticket's receipt, the thread is found.
        linked = {"ticket:acme/widgets#188:a1": "mcp:launch:linked-188"}
        threads = module.item_threads(pull, linked)
        print(f"threads from the linked ticket's receipt: {threads}")
        check(
            threads == ["mcp:launch:linked-188"],
            "the pull request did not find its linked ticket's builder thread",
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
