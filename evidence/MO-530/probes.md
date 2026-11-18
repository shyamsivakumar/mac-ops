# MO-530 · deny rules: what was probed

Ticket: mac-ops #530 (MO-1081). Approved by Shyam 2026-11-17 ("deny-rules":
yes). This is a tightening-only change: no allow rule is added anywhere.

- Source list: `runtime/agents/deny-rules.json`.
- Installer: `scripts/install_deny_rules.py` (install, status, uninstall).
- Probes: `evidence/MO-530/probes.py` (output in `probes.txt`).
- Docs: `docs/deny-rules.md`.

## Enforcement points and how each was probed

| Point | Installed artifact | Probe |
| --- | --- | --- |
| pi: `~/.pi/agent`, `agent-minimax`, `agent-glm`, `agent-deepseek`, `agent-openai-api`, `agent-anthropic-api` | `extensions/deny-guard.ts` in each directory | `evidence/MO-530/pi-guard-probe.ts` loads the installed file the way pi loads it and sends the real `tool_call` event shapes |
| Claude Code (`T3 claudeAgent`, Claude Code tabs) | `permissions.deny` in `~/.claude/settings.json` | `not run` offline: Claude Code evaluates this list in-session, so reading the file back would prove only that an entry was written. Each row names the live check to record the decision; the installed entries are also asserted by `tests/test_install_deny_rules.py` |
| Claude Code, merge role and remote-any push | `PreToolUse` hook `~/.claude/hooks/deny-merge-guard.py` | probe pipes the real hook payload: unpinned denied, pinned as a builder denied, pinned from a gate role allowed, a pin that is not a merge argument denied, `main`/`master` push on a second remote denied |
| Task-branch push stays allowed | n/a | scratch repo and scratch bare remote under `$TMPDIR`, real `git push` of `t3/deny-probe` |

## Live block in a pi session

This ticket was built in `~/.pi/agent-deepseek`, which has the guard
installed. Asking that session to read a file under the Ascend tree returned:

```
mac-ops deny rules (#530): reads and edits under ~/Code/slash-eureka (Ascend)
are denied. This is machine-enforced; route the work instead of working
around it.
```

The tool never ran. The same session also had a write whose content merely
mentioned `.env` refused by an earlier revision of the guard; that is fixed
(only path-bearing keys are checked as paths, covered by
`tests/test_install_deny_rules.py::GuardTest`), because otherwise agents could
not write about the list itself.

## Probe results

`python3 evidence/MO-530/probes.py` → `23 passed, 0 failed, 6 not run`, see
`probes.txt`. The six `not run` rows are the Claude `permissions.deny`
entries: Claude Code evaluates them inside a session, so the probe names the
live check instead of counting the file's text as a refusal. The rows that
did run are decisions taken by the enforcement points on scratch inputs, for
all six pi instances and for Claude Code:

- read under `~/Code/slash-eureka` refused
- edit and write of a fake `.env` refused, `bash cat` of it refused
- `bash cat` of an ssh-directory file refused; one `ls` of it allowed, and
  `ls ~/.ssh; cat ~/.ssh/id_ed25519` refused
- force-push, force-push-with-lease refused
- push to `main` and `master` refused, including on a second remote, and
  refused when `main` is the destination of a refspec (`feature:main`,
  `:main`) even though the source is not a protected ref
- a task branch whose name starts with a protected one (`main.fix`, `main/fix`)
  allowed, because the rule compares the complete destination ref, not a prefix,
  and `main:task-530` allowed because a protected source writing a task branch
  is a task-branch push
- `gh pr merge` refused with no pin, and refused with a pin when the caller is
  not a gate; a pin quoted inside another argument, including a pin and flag
  written inside a quoted multiword PR subject, is not a pin
- `gh pr merge ... --match-head-commit <head>` allowed only from the gate role
  (dry run only; nothing was merged). The role is provisioned by the trusted
  launcher: `coordinator/overnight/lane_driver.py` sets `MAC_OPS_ROLE=gate` on
  the pinned merge it runs, and the overnight selftest asserts it. The T3
  thread-launch call has no environment field, so a launched agent thread
  cannot be handed a role by the launch input. A dedicated provider instance
  carrying the role is the right channel and T3 does read a new instance from
  `~/.t3/userdata/settings.json` without a restart, but a second `claudeAgent`
  instance reports `Provider executable is not installed` and cannot launch, so
  an agent-typed merge stays refused until T3 can launch it.
- task-branch push to a scratch remote allowed, and the scratch remote has no
  `main` branch

No real secret was read: the `.env` used is `FAKE_API_KEY=not-a-real-secret`
in a scratch folder. No real push happened: the remote is a local bare repo.

## Scope

In: the deny list and its install. Out: any allow rule, any widening, the
coordinator's guard (`~/.pi/agent-coordinator/extensions/coordinator.ts`).
