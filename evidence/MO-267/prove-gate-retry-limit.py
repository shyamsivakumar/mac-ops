#!/usr/bin/env python3
"""Prove the gate retry limit of coordq without the live queue.

The proof runs the real `coordq gatekeep --dry-run` against a temp queue, a
stub `gh` and a stub `t3mcp`, with the queue seeded to the four states the
retry has to tell apart:

1. a head retried twice without a verdict is given up, one line, and no
   `would queue gate:` line for it,
2. a head with no retry behind it still gets its first retry,
3. a head that is new to the gate is still queued,
4. a given-up head whose sha changed is retried again, because the record
   is kept per head.

The same script proves a coordq file of another revision, so the run before
the change and the run after it use one harness:

    git show origin/main:coordinator/bin/coordq > /tmp/coordq-before
    python3 evidence/MO-267/prove-gate-retry-limit.py /tmp/coordq-before
    python3 evidence/MO-267/prove-gate-retry-limit.py

Run it from the mac-ops checkout.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COORDQ = ROOT / "coordinator" / "bin" / "coordq"

STUB_GH = '''#!/usr/bin/env python3
import json, os, sys
fixture = json.load(open(os.environ["GH_FIXTURE"]))
args = sys.argv[1:]
if args[:2] == ["api", "user"]:
    print(fixture["login"])
    sys.exit(0)
endpoint = args[-1]
if "/pulls" in endpoint:
    payload = fixture["pulls"]
elif "/comments" in endpoint:
    number = endpoint.split("/issues/")[1].split("/")[0]
    payload = fixture["issues"].get(number, {}).get("comments", [])
elif "/issues/" in endpoint:
    number = endpoint.split("/issues/")[1].split("/")[0]
    payload = fixture["issues"].get(number, {"number": int(number), "title": ""})
elif "/statuses" in endpoint:
    payload = fixture.get("statuses", [])
else:
    payload = []
print(json.dumps([payload]))
'''

STUB_T3MCP = '''#!/usr/bin/env python3
import json, sys
args = json.loads(sys.stdin.read() or "{}")
tool = sys.argv[2]
if tool == "t3_thread_list":
    print(json.dumps({"total": 0, "threads": []}))
elif "runLimit" in args:
    # The builder thread: it ran MiniMax, so the reviewer is Opus.
    print(json.dumps({"thread": {"threadId": args["threadId"],
                                 "providerInstanceId": "minimax",
                                 "model": "minimax/MiniMax-M3.1-Flash"},
                      "recentRuns": [{"executedModel": "minimax/MiniMax-M3.1-Flash"}]}))
else:
    # The gate thread: it failed before it could write a message, so there
    # is no verdict and no executed model.
    print(json.dumps({"thread": {"threadId": args.get("threadId"), "status": "failed"},
                      "items": [{"type": "user_message", "text": "review the diff"}],
                      "recentRuns": [{"executedModel": None}]}))
'''

# The reviewer fails before it can write a message, so the gate thread of
# every seeded head ends failed with no verdict.
DEAD_GATE_RECEIPTS = {"gate:acme/widgets#7:head7": "gate-7",
                      "gate:acme/widgets#8:head8": "gate-8",
                      "req-70": "builder-70", "req-80": "builder-80",
                      "req-100": "builder-100", "req-120": "builder-120"}

FAILURES = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f": {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def pull(number, head, issue):
    return {"number": number, "draft": False, "head": {"sha": head},
            "body": f"Refs #{issue}\n\nBuilder check: PASS {head}\n"}


def receipt(request_id):
    return {"user": {"login": "shyamsivakumar"},
            "body": '<!-- coordinator-ticket {"kind":"receipt","attempt":1,"requestId":"%s"} -->'
                    % request_id}


def build_fixture():
    return {
        "login": "shyamsivakumar",
        "pulls": [pull(7, "head7", 70), pull(8, "head8", 80),
                  pull(10, "head10", 100), pull(12, "head12", 120)],
        "issues": {
            "70": {"title": "WID-70 · retried twice", "comments": [receipt("req-70")]},
            "80": {"title": "WID-80 · never retried", "comments": [receipt("req-80")]},
            "100": {"title": "WID-100 · new head", "comments": [receipt("req-100")]},
            # The record of this pull request names an older head.
            "120": {"title": "WID-120 · changed head", "comments": [receipt("req-120")]},
        },
        "statuses": [],
    }


def build_threads():
    return {"list": [], "read": {}}


def write(path, text, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(mode)


def seed_queue():
    """The gate state of the four pull requests.

    `at` is far enough back that the backoff of a retried head never holds
    a retry back: this proof is about the limit, not the wait.
    """
    return {"next": 1, "items": [], "gatedHeads": {
        "gate:acme/widgets#7:head7": {"id": 4, "retries": 2, "at": 0.0, "givenUp": False},
        "gate:acme/widgets#8:head8": {"id": 5, "retries": 0, "at": None, "givenUp": False},
        "gate:acme/widgets#12:head12-old": {"id": 6, "retries": 2, "at": 0.0, "givenUp": True},
    }}


def main():
    coordq = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_COORDQ
    temp = Path(tempfile.mkdtemp(prefix="gate-retry-proof-"))
    home, queue, bin_dir = temp / "home", temp / "queue", temp / "bin"
    write(bin_dir / "gh", STUB_GH, 0o755)
    write(bin_dir / "t3mcp", STUB_T3MCP, 0o755)
    write(queue / "config.json", json.dumps({"cap": 5}))
    write(queue / "queue.json", json.dumps(seed_queue()))
    write(queue / "dispatch-receipts.json", json.dumps(DEAD_GATE_RECEIPTS))
    write(queue / "gh-fixture.json", json.dumps(build_fixture()))
    write(queue / "threads.json", json.dumps(build_threads()))
    write(home / ".coordinator" / "tickets.json", json.dumps(
        {"repos": {"acme/widgets": {"key": "WID", "projectId": "mcp:proof"}}}))
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "COORDQ_DIR": str(queue),
        "COORDQ_T3MCP": str(bin_dir / "t3mcp"),
        "GH_FIXTURE": str(queue / "gh-fixture.json"),
        # The queue is a temp one, and the proof must not wait for a backoff.
        "COORDQ_GATE_RETRY_BACKOFF": "0",
    }
    run = subprocess.run([sys.executable, str(coordq), "gatekeep", "--dry-run"],
                         env=env, capture_output=True, text=True, cwd=str(ROOT))
    out = run.stdout + run.stderr
    print(f"--- coordq {coordq}")
    print(out.strip())
    lines = [line for line in out.splitlines() if line.startswith("would queue gate:")]
    gave_up = [line for line in out.splitlines() if line.startswith("gave up ")]
    check("a head retried twice is not queued again",
          not any("acme/widgets#7:" in line for line in lines), out.strip())
    check("a head retried twice is named once as given up",
          len(gave_up) == 1 and "gate:acme/widgets#7:head7" in gave_up[0],
          json.dumps(gave_up))
    check("a head with no retry behind it still gets its first retry",
          any("acme/widgets#8:head8" in line for line in lines))
    check("a new head is queued", any("acme/widgets#10:head10" in line for line in lines))
    check("a given-up head whose sha changed is retried again",
          any("acme/widgets#12:head12" in line for line in lines))
    if FAILURES:
        print(f"\nFAIL: {len(FAILURES)} failed check(s)")
        return 1
    print("\nPASS: every check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
