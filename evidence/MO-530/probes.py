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

PR_TEXT = "Merges into main. Rule: no git push origin main, no git push --force."
# (label, command, refused). The protected-branch rule decides only from the
# destination ref of a real git push: text that names a protected branch or
# describes the rule is never a push to it.
DESTINATION_ROWS = [
    (
        "task-branch push in the same command as PR text naming main",
        f"git push -u origin t3/deny-probe && gh pr create --title 'Deny rules' --body '{PR_TEXT}'",
        False,
    ),
    (
        "task-branch push, then a PR body heredoc that names a main push",
        "git push origin t3/deny-probe\ngh pr create --body-file - <<'EOF'\ngit push origin main\nEOF",
        False,
    ),
    (
        "task-branch push, then a PR body in a command substitution heredoc",
        "git push origin t3/deny-probe && gh pr edit 531 --body \"$(cat <<'EOF'\nNever git push origin main\nEOF\n)\"",
        False,
    ),
    (
        "hc send whose text mentions the push rule and the branch name",
        "hc send coordinator 'Deny rules: no push to main or master, no git push --force, no gh pr merge for a builder'",
        False,
    ),
    (
        "hc send with an unquoted push command spelled out",
        "hc send coordinator git push origin main is denied",
        False,
    ),
    (
        "hc send whose text names the merge command",
        "hc send coordinator 'Builders never run gh pr merge; only a gate with a pinned head does'",
        False,
    ),
    (
        "task-branch push, then a PR body heredoc that names a merge",
        "git push origin t3/deny-probe\ngh pr create --body-file - <<'EOF'\nAfter checks pass: gh pr merge 531 --squash\nEOF",
        False,
    ),
    (
        "commit message that names the merge command",
        "git commit -m 'Deny gh pr merge for builders'",
        False,
    ),
    (
        "real merge after a message that names it",
        "hc send coordinator 'gh pr merge is gated' && gh pr merge 531 --squash",
        True,
    ),
    ("push HEAD to a protected branch", "git push origin HEAD:main", True),
    (
        "push HEAD to a full protected ref",
        "git push origin HEAD:refs/heads/master",
        True,
    ),
    (
        "push with a plus-prefixed protected destination",
        "git push origin +HEAD:main",
        True,
    ),
    ("push that deletes a protected branch", "git push origin :main", True),
    (
        "push main after a task-branch push in one command",
        "git push origin t3/deny-probe && git push origin main",
        True,
    ),
    (
        "push main after a PR text mention in one command",
        f"gh pr edit 531 --body '{PR_TEXT}' && git push -u origin main",
        True,
    ),
    ("force-push of a task branch", "git push --force origin t3/deny-probe", True),
    ("short force flag", "git push -f origin t3/deny-probe", True),
    ("force with lease", "git push --force-with-lease origin t3/deny-probe", True),
    ("plus-prefixed task-branch refspec", "git push origin +t3/deny-probe", True),
]

MAIN_REPO = SCRATCH / "repo-main"
TASK_REPO = SCRATCH / "repo-task"
# (label, command, refused, repo the command runs in). A push with no refspec
# writes the checked-out branch and its upstream, so the repo decides it; bulk
# pushes and gh global options are refused or allowed from any repo.
CWD_ROWS = [
    ("bare push on main (upstream origin/main)", "git push", True, MAIN_REPO),
    ("push to origin with no refspec on main", "git push -u origin", True, MAIN_REPO),
    ("push HEAD on main", "git push origin HEAD", True, MAIN_REPO),
    ("bare push on a task branch", "git push", False, TASK_REPO),
    ("push to origin with no refspec on a task branch", "git push -u origin", False, TASK_REPO),
    ("explicit task-branch push from a task branch", "git push origin t3/deny-probe", False, TASK_REPO),
    ("--all push from a task branch", "git push --all origin", True, TASK_REPO),
    ("--mirror push from a task branch", "git push --mirror origin", True, TASK_REPO),
    ("matching refspec push from a task branch", "git push origin :", True, TASK_REPO),
    ("bare push on main reached with git -C", f"git -C {MAIN_REPO} push", True, TASK_REPO),
    ("bare push on main reached with cd", f"cd {MAIN_REPO} && git push", True, TASK_REPO),
    ("gh -R x/y pr merge 1 from a builder", "gh -R x/y pr merge 1", True, TASK_REPO),
    ("gh --repo=x/y pr merge 1 from a builder", "gh --repo=x/y pr merge 1", True, TASK_REPO),
    ("gh -R x/y pr view 1", "gh -R x/y pr view 1", False, TASK_REPO),
]

results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool | None, detail: str) -> None:
    """Record one probe result. `None` means the probe did not run: it is
    reported, never counted as a pass."""
    status = "not run" if ok is None else ("PASS" if ok else "FAIL")
    results.append((status, name, detail))
    print(f"{status} {name}: {detail}", flush=True)


def pi_decisions(guard: Path, events: list[dict]) -> list[dict]:
    events_path = SCRATCH / "events.json"
    events_path.write_text(json.dumps(events, indent=2))
    if not BUN.is_file():
        raise SystemExit(f"bun not found at {BUN}")
    proc = subprocess.run(
        [str(BUN), str(HERE / "pi-guard-probe.ts"), str(guard), str(events_path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if proc.returncode != 0:
        raise SystemExit(f"guard probe failed: {proc.stderr}\n{proc.stdout}")
    return json.loads(proc.stdout)


def blocked(decision: dict | None) -> bool:
    return bool(decision and decision.get("block"))


def reason(decision: dict | None) -> str:
    return (decision or {}).get("reason", "")


def hook_decision(
    command: str, role: str | None = None, cwd: Path | None = None
) -> dict | None:
    env = {k: v for k, v in os.environ.items() if k != "MAC_OPS_ROLE"}
    if role is not None:
        env["MAC_OPS_ROLE"] = role
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": command},
                **({"cwd": str(cwd)} if cwd else {}),
            }
        ),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env=env,
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
            "event": {
                "toolName": "bash",
                "input": {"command": "git push --force origin main"},
            },
        },
        {
            "label": "force-push with lease",
            "cwd": str(SCRATCH),
            "event": {
                "toolName": "bash",
                "input": {"command": "git push --force-with-lease origin t3/x"},
            },
        },
        {
            "label": "push to main",
            "cwd": str(SCRATCH),
            "event": {"toolName": "bash", "input": {"command": "git push origin main"}},
        },
        {
            "label": "push to master",
            "cwd": str(SCRATCH),
            "event": {
                "toolName": "bash",
                "input": {"command": "git push origin HEAD:master"},
            },
        },
        {
            "label": "push to main on a second remote",
            "cwd": str(SCRATCH),
            "event": {"toolName": "bash", "input": {"command": "git push other main"}},
        },
        {
            "label": "one directory listing of the ssh directory",
            "cwd": str(SCRATCH),
            "event": {"toolName": "bash", "input": {"command": "ls -la ~/.ssh"}},
        },
        {
            "label": "a listing followed by a key read",
            "cwd": str(SCRATCH),
            "event": {
                "toolName": "bash",
                "input": {"command": "ls ~/.ssh; cat ~/.ssh/id_ed25519"},
            },
        },
        {
            "label": "unpinned gh pr merge",
            "cwd": str(SCRATCH),
            "event": {
                "toolName": "bash",
                "input": {"command": "gh pr merge 531 --squash"},
            },
        },
        {
            "label": "pinned gh pr merge as a builder (dry run, never executed)",
            "cwd": str(SCRATCH),
            "event": {"toolName": "bash", "input": {"command": PINNED}},
        },
        {
            "label": "pinned gh pr merge from a gate role (dry run, never executed)",
            "cwd": str(SCRATCH),
            "env": {"MAC_OPS_ROLE": "gate"},
            "event": {"toolName": "bash", "input": {"command": PINNED}},
        },
        {
            "label": "pin quoted inside a multiword PR subject",
            "cwd": str(SCRATCH),
            "env": {"MAC_OPS_ROLE": "gate"},
            "event": {
                "toolName": "bash",
                "input": {
                    "command": "gh pr merge 531 --squash --subject 'Merge --match-head-commit "
                    + "a" * 40
                    + "'"
                },
            },
        },
        {
            "label": "push a task branch",
            "cwd": str(SCRATCH),
            "event": {
                "toolName": "bash",
                "input": {"command": "git push --set-upstream origin t3/deny-probe"},
            },
        },
        {
            "label": "push a task branch named main.fix",
            "cwd": str(SCRATCH),
            "event": {
                "toolName": "bash",
                "input": {"command": "git push origin main.fix"},
            },
        },
        {
            "label": "push a task branch named main/fix",
            "cwd": str(SCRATCH),
            "event": {
                "toolName": "bash",
                "input": {"command": "git push origin main/fix"},
            },
        },
        {
            "label": "push to main on a second remote",
            "cwd": str(SCRATCH),
            "event": {
                "toolName": "bash",
                "input": {"command": "git push upstream main"},
            },
        },
        {
            "label": "push a task branch from a protected source ref (main:task-530)",
            "cwd": str(SCRATCH),
            "event": {
                "toolName": "bash",
                "input": {"command": "git push origin main:task-530"},
            },
        },
        {
            "label": "push to main as a refspec destination (feature:main)",
            "cwd": str(SCRATCH),
            "event": {
                "toolName": "bash",
                "input": {"command": "git push origin feature:main"},
            },
        },
    ]
    events += [
        {
            "label": label,
            "cwd": str(SCRATCH),
            "event": {"toolName": "bash", "input": {"command": command}},
        }
        for label, command, _ in DESTINATION_ROWS
    ]
    events += [
        {
            "label": label,
            "cwd": str(cwd),
            "event": {"toolName": "bash", "input": {"command": command}},
        }
        for label, command, _, cwd in CWD_ROWS
    ]
    expect_block = [
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        False,
        True,
        True,
        True,
        False,
        True,
        False,
        False,
        False,
        True,
        False,
        True,
    ]
    expect_block += [refused for _, _, refused in DESTINATION_ROWS]
    expect_block += [refused for _, _, refused, _ in CWD_ROWS]
    for instance in PI_INSTANCES:
        guard = HOME / ".pi" / instance / "extensions/deny-guard.ts"
        if not guard.is_file():
            record(f"pi guard installed: {guard}", False, "missing")
            continue
        decisions = pi_decisions(guard, events)
        ok = True
        details = []
        ok = ok and len(decisions) == len(expect_block)
        for index, item in enumerate(decisions):
            want = expect_block[index]
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
    """Claude Code decisions, taken from the enforcement points themselves.

    `permissions.deny` is evaluated by Claude Code inside a session. Reading
    the file back only proves an entry was written, not that a call is
    refused, so those rows are reported `not run` with the check to make; they
    are never counted as passes. The rules that live in the PreToolUse hook
    are exercised on the hook's real payload, which is the decision Claude
    Code acts on.
    """
    settings = json.loads(SETTINGS.read_text())
    deny = (settings.get("permissions") or {}).get("deny") or []
    for name, entry in (
        ("read under slash-eureka", "Read(~/Code/slash-eureka/**)"),
        ("edit under slash-eureka", "Edit(~/Code/slash-eureka/**)"),
        ("read an env file", "Read(**/.env)"),
        ("edit an env file", "Edit(**/.env)"),
        ("read the auth file", "Read(**/auth.json)"),
        ("read the ssh directory", "Read(~/.ssh/**)"),
        ("read a token file", "Read(**/*token*.json)"),
    ):
        present = entry in deny
        record(
            f"claude permissions.deny: {name}",
            None if present else False,
            (
                f"{entry} is installed; Claude evaluates it in-session, so run "
                f"`claude -p '{name}'` in a scratch folder to record the decision"
                if present
                else f"MISSING {entry}"
            ),
        )
    commands = [
        h.get("command", "")
        for block in (settings.get("hooks") or {}).get("PreToolUse") or []
        for h in block.get("hooks") or []
    ]
    registered = [c for c in commands if "deny-merge-guard.py" in c]
    record(
        "claude PreToolUse hook registered in settings.json",
        len(registered) == 1,
        registered[0] if registered else "MISSING",
    )
    cases = (
        (
            "unpinned gh pr merge",
            "gh pr merge 531 -R shyamsivakumar/mac-ops --squash",
            None,
            "deny",
        ),
        ("pinned gh pr merge as a builder", PINNED, None, "deny"),
        ("pinned gh pr merge from a gate role (not executed)", PINNED, "gate", "allow"),
        (
            "pin that is not a merge argument",
            "gh pr merge 531 --squash --body 'pin 5d3f2c1a4b5e6f70819283a4b5c6d7e8f9011223'",
            "gate",
            "deny",
        ),
        (
            "a pin quoted inside a multiword PR subject",
            "gh pr merge 531 --squash --subject 'Merge --match-head-commit 5d3f2c1a4b5e6f70819283a4b5c6d7e8f9011223'",
            "gate",
            "deny",
        ),
        ("push to master on a second remote", "git push other master", None, "deny"),
        ("force-push on a second remote", "git push -f other t3/x", None, "deny"),
        (
            "push a task branch",
            "git push --set-upstream origin t3/deny-probe",
            None,
            "allow",
        ),
        (
            "push a branch named main.fix (a task branch, not main)",
            "git push origin main.fix",
            None,
            "allow",
        ),
        (
            "push a branch named main/fix (a task branch, not main)",
            "git push origin main/fix",
            None,
            "allow",
        ),
        ("push to main on a second remote", "git push upstream main", None, "deny"),
        (
            "push a task branch from a protected source ref (main:task-530)",
            "git push origin main:task-530",
            None,
            "allow",
        ),
        (
            "push to main as a refspec destination (feature:main)",
            "git push origin feature:main",
            None,
            "deny",
        ),
    )
    cases += tuple(
        (label, command, None, "deny" if refused else "allow")
        for label, command, refused in DESTINATION_ROWS
    )
    cases += tuple(
        (label, command, None, "deny" if refused else "allow", cwd)
        for label, command, refused, cwd in CWD_ROWS
    )
    for label, command, role, want, *where in cases:
        decision = hook_decision(command, role, *where)
        got = (decision or {}).get("permissionDecision", "allow")
        record(
            f"claude hook: {label}",
            got == want,
            f"{got} ({str((decision or {}).get('permissionDecisionReason', 'no decision'))[:70]})",
        )


def probe_task_branch_push() -> None:
    remote = SCRATCH / "remote.git"
    repo = SCRATCH / "repo"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True, timeout=60)
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo)], check=True, timeout=60
    )
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
    subprocess.run(
        ["git", "-C", str(repo), "checkout", "-q", "-b", branch], check=True, timeout=60
    )
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
        check=False,
        timeout=120,
    )
    refs = subprocess.run(
        ["git", "-C", str(remote), "for-each-ref", "--format=%(refname)"],
        capture_output=True,
        text=True,
        check=False,
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
        [
            sys.executable,
            str(HERE.parents[1] / "scripts/install_deny_rules.py"),
            "status",
        ],
        capture_output=True,
        text=True,
        check=False,
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


def make_scratch_repos() -> None:
    for repo, branch, upstream in (
        (MAIN_REPO, "main", "refs/heads/main"),
        (TASK_REPO, "t3/deny-probe", "refs/heads/t3/deny-probe"),
    ):
        subprocess.run(["git", "init", "-q", "-b", branch, str(repo)], check=True, timeout=60)
        for key, value in (("remote", "origin"), ("merge", upstream)):
            subprocess.run(
                ["git", "-C", str(repo), "config", f"branch.{branch}.{key}", value],
                check=True,
                timeout=60,
            )


def main() -> int:
    make_scratch_repos()
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
    not_run = [r for r in results if r[0] == "not run"]
    passed = len(results) - len(failed) - len(not_run)
    print(
        f"\n{passed} passed, {len(failed)} failed, {len(not_run)} not run",
        flush=True,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
