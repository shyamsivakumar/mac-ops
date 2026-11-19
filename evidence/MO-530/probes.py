#!/usr/bin/env python3
"""Scratch probes for the mac-ops deny rules (#530).

Installs the rules into a scratch home with `install --root`, then drives each
installed enforcement point on its real payload: the six pi deny guards loaded
the way pi loads them (bun, tool_call events) and the Claude PreToolUse hook
(the hook payload Claude Code sends). Nothing reads or writes the real
~/.claude, ~/.local or pi config, no real secret is read, and no push leaves
the machine.

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

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BUN = Path.home() / ".bun/bin/bun"
SCRATCH = Path(
    tempfile.mkdtemp(
        prefix="deny-rules-probe-", dir=os.environ.get("TMPDIR", tempfile.gettempdir())
    )
).resolve()
HOME = SCRATCH / "home"
HOOK = HOME / ".claude/hooks/deny-merge-guard.py"
SETTINGS = HOME / ".claude/settings.json"
PI_INSTANCES = [
    "agent",
    "agent-minimax",
    "agent-glm",
    "agent-deepseek",
    "agent-openai-api",
    "agent-anthropic-api",
]
FAKE_ENV = SCRATCH / "app/.env"
ASCEND_FILE = HOME / "Code/slash-eureka/README.md"
PIN = "5d3f2c1a4b5e6f70819283a4b5c6d7e8f9011223"
PINNED = f"gh pr merge 531 -R shyamsivakumar/mac-ops --squash --match-head-commit {PIN}"
PR_TEXT = "Merges into main. Rule: no git push origin main, no git push --force."
GATE = {"MAC_OPS_ROLE": "gate"}

# (label, command, refused, env). The push rule decides only from destinations
# written in the command; text that names a protected branch is never a push.
ROWS = [
    (
        "task-branch push beside PR text naming main",
        f"git push -u origin t3/deny-probe && gh pr create --title T --body '{PR_TEXT}'",
        False,
        {},
    ),
    (
        "task-branch push, then a PR heredoc naming a main push",
        "git push origin t3/deny-probe\ngh pr create --body-file - <<'EOF'\ngit push origin main\nEOF",
        False,
        {},
    ),
    (
        "task-branch push, then a substitution heredoc naming a main push",
        "git push origin t3/deny-probe && gh pr edit 531 --body \"$(cat <<'EOF'\nNever git push origin main\nEOF\n)\"",
        False,
        {},
    ),
    (
        "hc send naming the push rule",
        "hc send coordinator 'Deny rules: no push to main or master, no git push --force, no gh pr merge for a builder'",
        False,
        {},
    ),
    (
        "hc send with an unquoted push command spelled out",
        "hc send coordinator git push origin main is denied",
        False,
        {},
    ),
    (
        "hc send naming the merge command",
        "hc send coordinator 'Builders never run gh pr merge; only a gate with a pinned head does'",
        False,
        {},
    ),
    (
        "PR heredoc naming a merge",
        "git push origin t3/deny-probe\ngh pr create --body-file - <<'EOF'\nAfter checks pass: gh pr merge 531 --squash\nEOF",
        False,
        {},
    ),
    (
        "commit message naming the merge command",
        "git commit -m 'Deny gh pr merge for builders'",
        False,
        {},
    ),
    (
        "real merge after a message naming it",
        "hc send coordinator 'gh pr merge is gated' && gh pr merge 531 --squash",
        True,
        {},
    ),
    ("push HEAD to a protected branch", "git push origin HEAD:main", True, {}),
    (
        "push HEAD to a full protected ref",
        "git push origin HEAD:refs/heads/master",
        True,
        {},
    ),
    ("plus-prefixed protected destination", "git push origin +HEAD:main", True, {}),
    ("push that deletes a protected branch", "git push origin :main", True, {}),
    (
        "main push after a task-branch push",
        "git push origin t3/deny-probe && git push origin main",
        True,
        {},
    ),
    (
        "main push after a PR text mention",
        f"gh pr edit 531 --body '{PR_TEXT}' && git push -u origin main",
        True,
        {},
    ),
    ("force-push of a task branch", "git push --force origin t3/deny-probe", True, {}),
    ("short force flag", "git push -f origin t3/deny-probe", True, {}),
    ("force with lease", "git push --force-with-lease origin t3/deny-probe", True, {}),
    ("plus-prefixed task-branch refspec", "git push origin +t3/deny-probe", True, {}),
    ("push main to a second remote", "git push other main", True, {}),
    ("push master to a url remote", "git push git@github.com:x/y.git master", True, {}),
    ("push a task branch", "git push --set-upstream origin t3/deny-probe", False, {}),
    ("task branch named main.fix", "git push origin main.fix", False, {}),
    ("task branch named main/fix", "git push origin main/fix", False, {}),
    (
        "protected source, task-branch destination",
        "git push origin main:task-530",
        False,
        {},
    ),
    ("feature to main", "git push origin feature:main", True, {}),
    ("bare push on a task branch", "git push", True, {}),
    ("bare push with an upstream flag", "git push -u origin", True, {}),
    ("remote alone", "git push origin", True, {}),
    ("HEAD alone", "git push origin HEAD", True, {}),
    ("--all", "git push --all origin", True, {}),
    ("--mirror", "git push --mirror origin", True, {}),
    ("matching refspec", "git push origin :", True, {}),
    ("wildcard refspec", "git push origin 'refs/heads/*:refs/heads/*'", True, {}),
    ("push main inside an if body", "if true; then git push origin main; fi", True, {}),
    ("push main inside a for loop", "for b in x; do git push origin main; done", True, {}),
    ("push main after a negation", "! git push origin main", True, {}),
    ("push main inside a brace group", "{ git push origin main; }", True, {}),
    ("bare push inside a while loop", "while true; do git push; done", True, {}),
    ("builder merge inside an if body", "if true; then gh pr merge 531 --squash; fi", True, {}),
    ("builder merge inside an until loop", "until false; do gh pr merge 531; done", True, {}),
    ("task-branch push inside an if body", "if true; then git push origin task; fi", False, {}),
    ("git push origin task", "git push origin task", False, {}),
    ("git push main task (a remote named main)", "git push main task", False, {}),
    ("git push origin HEAD:main", "git push origin HEAD:main", True, {}),
    ("git push origin task --force", "git push origin task --force", True, {}),
    ("git push origin +task", "git push origin +task", True, {}),
    ("gh -R x/y pr merge 1 from a builder", "gh -R x/y pr merge 1", True, {}),
    ("gh --repo=x/y pr merge 1 from a builder", "gh --repo=x/y pr merge 1", True, {}),
    ("gh pr -R x/y merge 1 from a builder", "gh pr -R x/y merge 1", True, {}),
    ("gh -R x/y pr view 1", "gh -R x/y pr view 1", False, {}),
    ("unpinned merge", "gh pr merge 531 -R shyamsivakumar/mac-ops --squash", True, {}),
    ("pinned merge as a builder", PINNED, True, {}),
    ("pinned merge from a gate role (not executed)", PINNED, False, GATE),
    (
        "pinned merge with -R before pr from a gate role",
        PINNED.replace("gh pr", "gh -R x/y pr"),
        False,
        GATE,
    ),
    (
        "pin mentioned in a body, not a merge argument",
        f"gh pr merge 531 --squash --body 'pin {PIN}'",
        True,
        GATE,
    ),
    (
        "pin quoted inside a multiword subject",
        f"gh pr merge 531 --squash --subject 'Merge --match-head-commit {PIN}'",
        True,
        GATE,
    ),
]
PI_ONLY_ROWS = [
    (
        "read under slash-eureka",
        {"toolName": "read", "input": {"path": str(ASCEND_FILE)}},
        True,
    ),
    ("edit an env file", {"toolName": "edit", "input": {"path": str(FAKE_ENV)}}, True),
    (
        "write an env file",
        {"toolName": "write", "input": {"path": str(FAKE_ENV)}},
        True,
    ),
    (
        "bash cat of an env file",
        {"toolName": "bash", "input": {"command": f"cat {FAKE_ENV}"}},
        True,
    ),
    (
        "bash cat of an ssh-directory file (not executed)",
        {"toolName": "bash", "input": {"command": "cat ~/.ssh/config"}},
        True,
    ),
    (
        "one directory listing of the ssh directory",
        {"toolName": "bash", "input": {"command": "ls -la ~/.ssh"}},
        False,
    ),
    (
        "a listing followed by a key read",
        {"toolName": "bash", "input": {"command": "ls ~/.ssh; cat ~/.ssh/id_ed25519"}},
        True,
    ),
    ("relative read while the shell is inside the Ascend tree", {"toolName": "bash", "input": {"command": "cat README.md"}, "cwd": str(HOME / "Code/slash-eureka/x")}, True),
    ("relative read in an ordinary directory", {"toolName": "bash", "input": {"command": "cat README.md"}, "cwd": str(HOME)}, False),
    (
        "write prose that mentions .env",
        {
            "toolName": "write",
            "input": {
                "path": str(SCRATCH / "d.md"),
                "content": "No reads of .env or ~/.ssh/id_ed25519.",
            },
        },
        False,
    ),
]

results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool | None, detail: str) -> None:
    status = "not run" if ok is None else ("PASS" if ok else "FAIL")
    results.append((status, name, detail))
    print(f"{status} {name}: {detail}", flush=True)


def run(command: list[str], **options) -> subprocess.CompletedProcess:
    return subprocess.run(
        command, capture_output=True, text=True, timeout=120, check=False, **options
    )


def hook_decision(command: str, env_extra: dict) -> dict | None:
    env = {k: v for k, v in os.environ.items() if k != "MAC_OPS_ROLE"} | env_extra
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(SCRATCH),
    }
    proc = run([sys.executable, str(HOOK)], input=json.dumps(payload), env=env)
    if proc.returncode != 0:
        raise SystemExit(f"hook failed: {proc.stderr}")
    return (
        json.loads(proc.stdout)["hookSpecificOutput"] if proc.stdout.strip() else None
    )


def probe_installer() -> None:
    script = [sys.executable, str(REPO / "scripts/install_deny_rules.py")]
    for action in ("install", "install", "status"):
        proc = run([*script, action, "--root", str(HOME)])
        if proc.returncode != 0:
            raise SystemExit(f"installer {action} failed: {proc.stderr}")
    status = json.loads(proc.stdout)
    record(
        "installer: install twice over a scratch home, then status",
        status["installed"],
        f"installed={status['installed']}",
    )
    record(
        "installer: every pi guard installed and current",
        all(v == "installed" for v in status["pi_guards"].values()),
        json.dumps(status["pi_guards"])[:120],
    )
    record(
        "installer: claude deny list complete",
        status["claude_deny_missing"] == [],
        f"missing={status['claude_deny_missing']}",
    )
    record("installer: merge hook file present", status["merge_hook_file"], str(HOOK))
    commands = [
        h.get("command", "")
        for block in json.loads(SETTINGS.read_text())["hooks"]["PreToolUse"]
        for h in block["hooks"]
    ]
    record(
        "claude PreToolUse hook registered once in settings.json",
        sum("deny-merge-guard.py" in c for c in commands) == 1,
        str(commands),
    )
    deny = json.loads(SETTINGS.read_text())["permissions"]["deny"]
    for name, entry in (
        ("read under slash-eureka", "Read(~/Code/slash-eureka/**)"),
        ("edit under slash-eureka", "Edit(~/Code/slash-eureka/**)"),
        ("read an env file", "Read(**/.env)"),
        ("edit an env file", "Edit(**/.env)"),
        ("read the auth file", "Read(**/auth.json)"),
        ("read the ssh directory", "Read(~/.ssh/**)"),
        ("read a token file", "Read(**/*token*.json)"),
    ):
        record(
            f"claude permissions.deny: {name}",
            None if entry in deny else False,
            f"{entry} installed; Claude evaluates it in a session, so the decision is not run here"
            if entry in deny
            else f"MISSING {entry}",
        )


def probe_claude_hook() -> None:
    for label, command, refused, env in ROWS:
        decision = hook_decision(command, env)
        got = (decision or {}).get("permissionDecision", "allow")
        detail = str((decision or {}).get("permissionDecisionReason", "no decision"))[
            :90
        ]
        record(
            f"claude hook: {label}",
            got == ("deny" if refused else "allow"),
            f"{got} ({detail})",
        )
    bare = hook_decision("git push", {})
    record(
        "claude hook: a bare push says to name the branch",
        "name the branch" in str((bare or {}).get("permissionDecisionReason")),
        "reason names `git push -u origin <task-branch>`",
    )


def probe_pi_guards() -> None:
    if not BUN.is_file():
        record("pi guards", None, f"bun not found at {BUN}")
        return
    events = [
        {
            "label": label,
            "env": env,
            "cwd": str(SCRATCH),
            "event": {"toolName": "bash", "input": {"command": command}},
        }
        for label, command, _, env in ROWS
    ]
    events += [
        {"label": label, "cwd": event.pop("cwd", str(SCRATCH)), "event": event}
        for label, event, _ in PI_ONLY_ROWS
    ]
    expected = [refused for _, _, refused, _ in ROWS] + [
        refused for _, _, refused in PI_ONLY_ROWS
    ]
    events_path = SCRATCH / "events.json"
    events_path.write_text(json.dumps(events))
    for instance in PI_INSTANCES:
        guard = HOME / ".pi" / instance / "extensions/deny-guard.ts"
        proc = run(
            [str(BUN), str(HERE / "pi-guard-probe.ts"), str(guard), str(events_path)]
        )
        if proc.returncode != 0:
            record(f"pi guard {instance}", False, proc.stderr[:200])
            continue
        for index, item in enumerate(json.loads(proc.stdout)):
            want = expected[index]
            blocked = bool((item["decision"] or {}).get("block"))
            record(
                f"pi guard {instance}: {item['label']}",
                blocked == want,
                "blocked" if blocked else "allowed",
            )


def probe_task_branch_push() -> None:
    remote, repo = SCRATCH / "remote.git", SCRATCH / "repo"
    who = ["-c", "user.name=probe", "-c", "user.email=probe@example.invalid"]
    for step in (
        ["git", "init", "--bare", "-q", str(remote)],
        ["git", "init", "-q", "-b", "main", str(repo)],
        [
            "git",
            *who,
            "-C",
            str(repo),
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "scratch",
        ],
        ["git", "-C", str(repo), "remote", "add", "origin", str(remote)],
        ["git", "-C", str(repo), "checkout", "-q", "-b", "t3/deny-probe"],
    ):
        run(step).check_returncode()
    pushed = run(
        [
            "git",
            "-C",
            str(repo),
            "push",
            "-q",
            "--set-upstream",
            "origin",
            "t3/deny-probe",
        ]
    )
    refs = run(
        ["git", "-C", str(remote), "for-each-ref", "--format=%(refname)"]
    ).stdout.split()
    record(
        "pushing a task branch is still allowed (scratch remote)",
        pushed.returncode == 0 and "refs/heads/t3/deny-probe" in refs,
        str(refs),
    )
    record(
        "scratch remote has no main branch", "refs/heads/main" not in refs, str(refs)
    )


def main() -> int:
    FAKE_ENV.parent.mkdir(parents=True)
    FAKE_ENV.write_text("FAKE_API_KEY=not-a-real-secret\n")
    HOME.mkdir()
    try:
        probe_installer()
        probe_claude_hook()
        probe_pi_guards()
        probe_task_branch_push()
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
    failed = [r for r in results if r[0] == "FAIL"]
    not_run = [r for r in results if r[0] == "not run"]
    print(
        f"\n{len(results) - len(failed) - len(not_run)} passed, {len(failed)} failed, {len(not_run)} not run",
        flush=True,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
