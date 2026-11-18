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
| Claude Code (`T3 claudeAgent`, Claude Code tabs) | `permissions.deny` in `~/.claude/settings.json` | probe asserts each list entry is present in the file the `claude` CLI reads |
| Claude Code, unpinned merge | `PreToolUse` hook `~/.claude/hooks/deny-merge-guard.py` | probe pipes the real hook payload: unpinned denied, pinned allowed |
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

`python3 evidence/MO-530/probes.py` → `23 passed, 0 failed`, see
`probes.txt`. It covers, for all six pi instances and for Claude Code:

- read under `~/Code/slash-eureka` refused
- edit and write of a fake `.env` refused, `bash cat` of it refused
- `bash cat` of an ssh-directory file refused
- force-push, force-push-with-lease refused
- push to `main` and `master` refused
- `gh pr merge` without `--match-head-commit` refused
- `gh pr merge ... --match-head-commit` allowed (dry run only; nothing was
  merged)
- task-branch push to a scratch remote allowed, and the scratch remote has no
  `main` branch

No real secret was read: the `.env` used is `FAKE_API_KEY=not-a-real-secret`
in a scratch folder. No real push happened: the remote is a local bare repo.

## Scope

In: the deny list and its install. Out: any allow rule, any widening, the
coordinator's guard (`~/.pi/agent-coordinator/extensions/coordinator.ts`).
