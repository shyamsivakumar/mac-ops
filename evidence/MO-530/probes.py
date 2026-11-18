#!/usr/bin/env python3
"""Scratch probes for the mac-ops deny rules (#530).

Each probe exercises one real enforcement point, never a real secret and
never a real push to a real remote:

- pi agents: the installed extensions/deny-guard.ts in every instance
  directory, loaded the way pi loads it, called with the tool_call event
  shapes pi sends.
- Claude Code: the installed ~/.claude/settings.json permissions.deny list
  and the installed ~/.claude/hooks/deny-merge-guard.py PreToolUse hook,
  called with the hook payload Claude Code sends.
- Pushing a task branch stays allowed: a scratch repo and a scratch bare
  remote, both under $TMPDIR. Nothing leaves the machine.

Run: python3 evidence/MO-530/probes.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HOME = Path.home()
HERE = Path(__file__).resolve().parent
BUN = Path.home() / ".bun/bin/bun"
TMP = Path(os.environ.get("TMPDIR", tempfile.gettempdir()))
PI_INSTANCES = [
    "agent",
    "agent-minimax",
    "agent-glm",
    "agent-deepseek",
    "agent-openai-api",
    "agent-anthropic-api",
]
SETTINGS = HOME / ".claude/settings.json"
HOOK = HOME / ".claude/hooks/deny-merge-guard.py"
SCRATCH = Path(tempfile.mkdtemp(prefix="deny-rules-probe-", dir=TMP))
FAKE_ENV = SCRATCH / "app/.env"
ASCEND_FILE = HOME / "Code/slash-eureka/README.md"
PINNED = (
    "gh pr merge 531 -R shyamsivakumar/mac-ops --squash "
    "--match-head-commit 5d3f2c1a4b5e6f70819283a4b5c6d7e8f9011223"
)

results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str) -> None:
    results.append(("PASS" if ok else "FAIL", name, detail))
    print(f"{results[-1][0]} {name}: {detail}", flush=True)


def pi_decisions(guard: Path, events: list[dict]) -> list[dict]:
    events_path = SCRATCH / "events.json"
    events_path.write_text(json.dumps(events, indent=2))
    if not BUN.is_file():
        raise SystemExit(f"bun not found at {BUN}")
    proc = subprocess.run(
        [str(BUN), str(HERE / "pi-guard-probe.ts"), str(guard), str(events_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise SystemExit(f"guard probe failed: {proc.stderr}\n{proc.stdout}")
    return json.loads(proc.stdout)


def blocked(decision: dict | None) -> bool:
    return bool(decision and decision.get("block"))


def reason(decision: dict | None) -> str:
    return (decision or {}).get("reason", "")


def hook_decision(command: str) -> dict | None:
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise SystemExit(f"hook failed: {proc.stderr}")
    if not proc.stdout.strip():
        return None
    return json.loads(proc.stdout)["hookSpecificOutput"]


def probe_pi_guards() -> None:
    events = [
        {
            "label": "read a file under ~/Code/slash-eureka",
            "cwd": str(SCRATCH),
            "event": {"toolName": "read", "input": {"path": str(ASCEND_FILE)}},
        },
        {
            "label": "edit an env file",
            "cwd": str(SCRATCH),
            "event": {"toolName": "edit", "input": {"path": str(FAKE_ENV)}},
        },
        {
            "label": "write an env file",
            "cwd": str(SCRATCH),
            "event": {"toolName": "write", "input": {"path": str(FAKE_ENV)}},
        },
        {
            "label": "bash cat of an env file",
            "cwd": str(SCRATCH),
            "event": {"toolName": "bash", "input": {"command": f"cat {FAKE_ENV}"}},
        },
        {
            "label": "bash cat of a file in the ssh directory (not executed)",
            "cwd": str(SCRATCH),
            "event": {"toolName": "bash", "input": {"command": "cat ~/.ssh/config"}},
        },
        {
            "label": "force-push",
            "cwd": str(SCRATCH),
            "event": {"toolName": "bash", "input": {"command": "git push --force origin main"}},
        },
        {
            "label": "force-push with lease",
            "cwd": str(SCRATCH),
            "event": {"toolName": "bash", "input": {"command": "git push --force-with-lease origin t3/x"}},
        },
        {
            "label": "push to main",
            "cwd": str(SCRATCH),
            "event": {"toolName": "bash", "input": {"command": "git push origin main"}},
        },
        {
            "label": "push to master",
            "cwd": str(SCRATCH),
            "event": {"toolName": "bash", "input": {"command": "git push origin HEAD:master"}},
        },
        {
            "label": "unpinned gh pr merge",
            "cwd": str(SCRATCH),
            "event": {"toolName": "bash", "input": {"command": "gh pr merge 531 --squash"}},
        },
        {
            "label": "pinned gate merge (dry run, never executed)",
            "cwd": str(SCRATCH),
            "event": {"toolName": "bash", "input": {"command": PINNED}},
        },
        {
            "label": "push a task branch",
            "cwd": str(SCRATCH),
            "event": {"toolName": "bash", "input": {"command": "git push --set-upstream origin t3/deny-probe"}},
        },
    ]
    expect_block = [True, True, True, True, True, True, True, True, True, True, False, False]
    for instance in PI_INSTANCES:
        guard = HOME / ".pi" / instance / "extensions/deny-guard.ts"
        if not guard.is_file():
            record(f"pi guard installed: {guard}", False, "missing")
            continue
        decisions = pi_decisions(guard, events)
        ok = True
        details = []
        for index, (item, want) in enumerate(zip(decisions, expect_block)):
            got = blocked(item["decision"])
            label = events[index]["label"]
            say = "blocked" if got else "allowed"
            if got:
                say += f" ({reason(item['decision'])[:60]}...)"
            details.append(f"{label} -> {say}")
            if got != want:
                ok = False
        record(
            f"pi guard {guard.parent.parent.name}",
            ok,
            "; ".join(details[:4]) + " ..." if ok else "; ".join(details),
        )


def probe_claude_settings() -> None:
    settings = json.loads(SETTINGS.read_text())
    deny = (settings.get("permissions") or {}).get("deny") or []
    required = {
        "read under slash-eureka": any(e.startswith("Read(") and "slash-eureka" in e for e in deny),
        "edit under slash-eureka": any(e.startswith("Edit(") and "slash-eureka" in e for e in deny),
        "read an env file": "Read(**/.env)" in deny,
        "edit an env file": "Edit(**/.env)" in deny,
        "read the auth file": "Read(**/auth.json)" in deny,
        "read the ssh directory": "Read(~/.ssh/**)" in deny,
        "force-push": "Bash(git push --force:*)" in deny and "Bash(git push -f:*)" in deny,
        "push to main": "Bash(git push origin main)" in deny,
        "push to master": "Bash(git push origin master)" in deny,
    }
    for name, present in required.items():
        record(f"claude permissions.deny: {name}", present, "present" if present else "MISSING")
    commands = [
        h.get("command", "")
        for block in (settings.get("hooks") or {}).get("PreToolUse") or []
        for h in block.get("hooks") or []
    ]
    registered = [c for c in commands if "deny-merge-guard.py" in c]
    record(
        "claude PreToolUse merge hook registered in settings.json",
        len(registered) == 1,
        registered[0] if registered else "MISSING",
    )
    unpinned = hook_decision("gh pr merge 531 -R shyamsivakumar/mac-ops --squash")
    record(
        "claude hook blocks unpinned gh pr merge",
        bool(unpinned and unpinned.get("permissionDecision") == "deny"),
        (unpinned or {}).get("permissionDecisionReason", "no decision")[:90],
    )
    pinned = hook_decision(PINNED)
    record(
        "claude hook allows the gate's pinned gh pr merge (not executed)",
        pinned is None,
        "no decision, command allowed to run" if pinned is None else json.dumps(pinned),
    )


def probe_task_branch_push() -> None:
    remote = SCRATCH / "remote.git"
    repo = SCRATCH / "repo"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True, timeout=60)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, timeout=60)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "probe",
        "GIT_AUTHOR_EMAIL": "probe@example.invalid",
        "GIT_COMMITTER_NAME": "probe",
        "GIT_COMMITTER_EMAIL": "probe@example.invalid",
    }
    (repo / "README.md").write_text("scratch\n")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True, timeout=60)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "scratch"],
        check=True,
        timeout=60,
        env=env,
    )
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", str(remote)],
        check=True,
        timeout=60,
    )
    branch = "t3/deny-probe"
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", branch], check=True, timeout=60)
    (repo / "probe.txt").write_text("branch push probe\n")
    subprocess.run(["git", "-C", str(repo), "add", "probe.txt"], check=True, timeout=60)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "branch push probe"],
        check=True,
        timeout=60,
        env=env,
    )
    push = subprocess.run(
        ["git", "-C", str(repo), "push", "-q", "--set-upstream", "origin", branch],
        capture_output=True,
        text=True,
        timeout=120,
    )
    refs = subprocess.run(
        ["git", "-C", str(remote), "for-each-ref", "--format=%(refname)"],
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.split()
    record(
        "pushing a task branch is still allowed (scratch remote)",
        push.returncode == 0 and f"refs/heads/{branch}" in refs,
        f"pushed to {remote}: {refs}",
    )
    record(
        "scratch remote has no main branch (nothing was pushed to main)",
        "refs/heads/main" not in refs,
        f"refs on scratch remote: {refs}",
    )


def probe_installer_status() -> None:
    proc = subprocess.run(
        [sys.executable, str(HERE.parents[1] / "scripts/install_deny_rules.py"), "status"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        record("installer status", False, proc.stderr.strip()[:200])
        return
    status = json.loads(proc.stdout)
    guards = status.get("pi_guards") or {}
    record(
        "installer status: every pi guard installed and current",
        bool(guards) and all(v == "installed" for v in guards.values()),
        json.dumps(guards),
    )
    record(
        "installer status: claude deny list complete",
        status.get("claude_deny_missing") == [],
        f"missing={status.get('claude_deny_missing')}",
    )
    record(
        "installer status: merge hook file present",
        bool(status.get("merge_hook_file")),
        str(HOOK),
    )


def main() -> int:
    if not FAKE_ENV.parent.is_dir():
        FAKE_ENV.parent.mkdir(parents=True)
    # A fake secret, only for the probes to be denied on. It is never read.
    FAKE_ENV.write_text("FAKE_API_KEY=not-a-real-secret\n")
    try:
        probe_installer_status()
        probe_pi_guards()
        probe_claude_settings()
        probe_task_branch_push()
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
    failed = [r for r in results if r[0] == "FAIL"]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
