#!/usr/bin/env python3
"""Prove the gatekeep candidate rules of coordq without the live queue.

The proof runs the real `coordq gatekeep` against a temp queue, a stub `gh`
and a stub `t3mcp`. It shows:

1. a pull request whose dispatch receipt names no builder run is gated from
   the builder thread of its ticket key,
2. the reviewer comes from the executed model of the builder run, so the
   reviewer never shares the vendor of the builder,
3. a router route that can run an Anthropic model gives no evidence, so the
   pull request is skipped and reported instead of guessed,
4. a head that is already in `gatedHeads` is not gated twice,
5. a pull request that is skipped on the same head three times is written to
   `queue/gatekeep-stuck.txt`, one line, and the file keeps only the pull
   requests that are still stuck.

Run it from the mac-ops checkout:

    python3 evidence/MO-237/prove-gatekeep-candidates.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COORDQ = ROOT / "coordinator" / "bin" / "coordq"

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
import json, os, sys
tool = sys.argv[2]
payload = sys.stdin.read()
with open(os.environ["STUB_LOG"], "a") as f:
    f.write(json.dumps({"tool": tool, "args": json.loads(payload or "{}")}) + "\\n")
threads = json.load(open(os.environ["STUB_THREADS"]))
if tool == "t3_thread_list":
    title = json.loads(payload).get("titleContains", "")
    matches = [t for t in threads["list"] if title in t["title"]]
    print(json.dumps({"total": 0, "threads": matches}))
elif tool == "t3_thread_read":
    thread_id = json.loads(payload)["threadId"]
    print(json.dumps(threads["read"].get(thread_id, {"thread": {}, "recentRuns": []})))
else:
    print(json.dumps({"ok": True, "tool": tool}))
'''

ROUTER = '''const ROUTES: Record<string, string[]> = {
\tstandard: ["minimax/MiniMax-M3.1-Flash:medium", "deepseek/deepseek-flash:medium", "openai/gpt-6.1-terra:medium"],
\tui: ["minimax/MiniMax-M3.1-Flash:medium", "pi-claude-cli/claude-sonnet-5-5:medium"],
};
'''

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
            "body": '<!-- coordinator-ticket {"kind":"receipt","attempt":1,"requestId":"%s"} -->' % request_id}


def build_fixture():
    return {
        "login": "shyamsivakumar",
        "pulls": [
            pull(7, "head7", 70),
            pull(8, "head8", 80),
            pull(9, "head9", 90),
            pull(11, "head11", 110),
        ],
        "issues": {
            "70": {"title": "WID-70 · the router build", "comments": [receipt("req-70")]},
            "80": {"title": "WID-80 · the claude build", "comments": [receipt("req-80")]},
            "90": {"title": "WID-90 · the build with no thread", "comments": [receipt("req-90")]},
            "110": {"title": "WID-110 · the ui route", "comments": [receipt("req-110")]},
        },
        "statuses": [],
    }


def build_threads():
    return {
        "list": [
            {"threadId": "th-70", "title": "WID-70 · the router build", "createdAt": "2026-01-01T00:00:00Z"},
            {"threadId": "th-80", "title": "WID-80 · the claude build", "createdAt": "2026-01-02T00:00:00Z"},
            {"threadId": "th-110", "title": "WID-110 · the ui route", "createdAt": "2026-01-03T00:00:00Z"},
            {"threadId": "th-70-old", "title": "WID-70 · an older build", "createdAt": "2025-12-01T00:00:00Z"},
            {"threadId": "th-gate", "title": "WID-70 review #7 head7", "createdAt": "2026-01-04T00:00:00Z"},
        ],
        "read": {
            "th-70": {"thread": {"providerInstanceId": "router", "model": "task/standard"},
                      "recentRuns": [{"executedModel": None}]},
            "th-80": {"thread": {"providerInstanceId": "claudeAgent", "model": "claude-opus-5-5"},
                      "recentRuns": [{"executedModel": "claude-opus-5-5"}]},
            "th-110": {"thread": {"providerInstanceId": "router", "model": "task/ui"},
                       "recentRuns": [{"executedModel": None}]},
        },
    }


def write(path, text, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(mode)


def run_gatekeep(env, cwd):
    return subprocess.run([sys.executable, str(COORDQ), "gatekeep"], env=env,
                          capture_output=True, text=True, cwd=str(cwd))


def gates_of(queue):
    items = json.loads((queue / "queue.json").read_text())["items"]
    return {item["args"]["title"].split(" review #")[1].split(" ")[0]: item
            for item in items if item["tool"] == "t3_thread_launch"}


def main():
    temp = Path(tempfile.mkdtemp(prefix="gatekeep-proof-"))
    home = temp / "home"
    queue = temp / "queue"
    bin_dir = temp / "bin"
    write(bin_dir / "gh", STUB_GH, 0o755)
    write(bin_dir / "t3mcp", STUB_T3MCP, 0o755)
    write(home / ".pi" / "agent" / "extensions" / "task-router.ts", ROUTER)
    write(queue / "config.json", json.dumps({"cap": 5}))
    write(queue / "queue.json", json.dumps({"next": 1, "items": [], "gatedHeads": {}}))
    write(queue / "dispatch-receipts.json", json.dumps({}))
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
        "STUB_THREADS": str(queue / "threads.json"),
        "STUB_LOG": str(queue / "calls.log"),
    }

    run = run_gatekeep(env, ROOT)
    gates = gates_of(queue)
    check("the receipt-less router build is gated", "7" in gates, run.stdout.strip() + run.stderr.strip())
    check("the claude build is gated", "8" in gates)
    check("the build with no thread is not gated", "9" not in gates)
    check("a route that can run claude is not gated", "11" not in gates)
    reviewer7 = gates.get("7", {}).get("args", {}).get("modelSelection", {})
    reviewer8 = gates.get("8", {}).get("args", {}).get("modelSelection", {})
    check("a non-claude builder gets Opus", reviewer7 == {"instanceId": "claudeAgent", "model": "claude-opus-5-5"},
          json.dumps(reviewer7))
    check("a claude builder gets Sol", reviewer8 == {"instanceId": "codex", "model": "gpt-6.1-sol"},
          json.dumps(reviewer8))
    check("the builder thread of the ticket key is used", "th-70" in (queue / "calls.log").read_text())

    run = run_gatekeep(env, ROOT)
    gates = gates_of(queue)
    check("a head in gatedHeads is not gated twice",
          len([i for i in json.loads((queue / "queue.json").read_text())["items"]
               if i["args"]["title"].startswith("WID-70 review #7")]) == 1)

    stuck_file = queue / "gatekeep-stuck.txt"
    for _ in range(2):
        run_gatekeep(env, ROOT)
    lines = stuck_file.read_text().splitlines() if stuck_file.exists() else []
    check("a pull request skipped three times on one head is stuck once",
          lines == ["acme/widgets#11 head11 executed model unavailable",
                    "acme/widgets#9 head9 builder run not found"], str(lines))
    status = json.loads(subprocess.run([sys.executable, str(COORDQ), "status"], env=env,
                                        capture_output=True, text=True).stdout)
    check("coordq status reports the stuck pull requests", status.get("stuck") == lines, json.dumps(status))

    # The builder thread of the stuck pull request appears: it is gated and it
    # leaves the stuck file.
    threads = build_threads()
    threads["list"].append({"threadId": "th-90", "title": "WID-90 · the build with no thread",
                            "createdAt": "2026-01-05T00:00:00Z"})
    threads["read"]["th-90"] = {"thread": {"providerInstanceId": "codex", "model": "gpt-6.1-sol"},
                                  "recentRuns": [{"executedModel": None}]}
    write(queue / "threads.json", json.dumps(threads))
    run_gatekeep(env, ROOT)
    gates = gates_of(queue)
    check("a pull request whose builder thread appears is gated", "9" in gates, run.stdout.strip())
    check("the gate of that pull request names the reviewer",
          gates.get("9", {}).get("args", {}).get("modelSelection") == {"instanceId": "claudeAgent", "model": "claude-opus-5-5"},
          json.dumps(gates.get("9", {}).get("args", {}).get("modelSelection", {})))

    run_gatekeep(env, ROOT)
    lines = stuck_file.read_text().splitlines() if stuck_file.exists() else []
    check("a gated pull request leaves the stuck file", lines == ["acme/widgets#11 head11 executed model unavailable"],
          str(lines))

    # A blocked model does not change the answer: the route is not evidence.
    blocks = home / ".pi" / "agent" / "task-router-blocks.json"
    write(blocks, json.dumps({"minimax/MiniMax-M3.1-Flash": {"until": 4102444800000, "reason": "proof"}}))
    run_gatekeep(env, ROOT)
    lines = stuck_file.read_text().splitlines() if stuck_file.exists() else []
    check("a blocked model does not guess an executed model",
          lines == ["acme/widgets#11 head11 executed model unavailable"], str(lines))

    print(f"\n{'PASS' if not FAILURES else 'FAIL'}: {len(FAILURES)} failed check(s)")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
