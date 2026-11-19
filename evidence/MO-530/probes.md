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

`python3 evidence/MO-530/probes.py` → `60 passed, 0 failed, 7 not run`, see
`probes.txt`. The seven `not run` rows are the Claude `permissions.deny`
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
  (dry run only; nothing was merged). The role is read from the launch
  environment only. The launcher that provisions it (`claudeAgentGate`) is part
  2 of #534, so until then every agent-typed merge stays refused.
- the protected-branch rule decides only from the destination ref of a real
  push, in the Claude hook and in all six pi guards:
  - allowed: a task-branch push in the same command as a PR body that names
    `main` (quoted, heredoc, and command-substitution heredoc forms); an `hc
    send` whose text mentions the rule, the branch name or a spelled-out push
  - refused: `HEAD:main`, `HEAD:refs/heads/master`, `+HEAD:main`, `:main`, and a
    real push of `main` after a task-branch push or a PR text mention in one
    command
  - bare push on main (upstream `origin/main`) refused, also `git push -u
    origin` and `git push origin HEAD`; the same bare pushes on a task branch
    allowed, and an explicit task-branch push allowed
  - a task-branch push to a remote named `main` allowed (git's dry run shows
    the task branch); an implicit push that `remote.origin.push` maps to `main`
    refused (destinations come from `git push --dry-run --porcelain`)
  - `--all`, `--mirror`, `:` and a wildcard refspec refused; a bare push on main
    reached with `git -C` or `cd` refused
  - `gh -R x/y pr merge 1` and `gh --repo=x/y pr merge 1` from a builder
    refused; `gh -R x/y pr view 1` allowed
  - refused as before: `--force`, `-f`, `--force-with-lease`, and a
    plus-prefixed task-branch refspec
  The probes ran against a scratch home (`install --root`), so the live
  `~/.claude` and `~/.pi` copies were not touched; reinstall with
  `python3 scripts/install_deny_rules.py install` to take the new guard live.
- task-branch push to a scratch remote allowed, and the scratch remote has no
  `main` branch

No real secret was read: the `.env` used is `FAKE_API_KEY=not-a-real-secret`
in a scratch folder. No real push happened: the remote is a local bare repo.

## Scope

In: the deny list and its install. Out: any allow rule, any widening, the
coordinator's guard (`~/.pi/agent-coordinator/extensions/coordinator.ts`).
