# Deny rules for agents

Machine-enforced deny list for agent permissions, approved by Shyam on
2026-11-17 (decisions board, "deny-rules": yes) and tracked as mac-ops #530.

Prose limits in `CLAUDE.md` and the scope files can be ignored by a model. A
deny rule blocks the tool before it runs, so the same list is installed where
each tool checks tools, and written into the scope files as prose.

## The list

1. No reads or edits under `~/Code/slash-eureka` (the Ascend repos: AUH, MCP,
   OPS, DBT, OMN).
2. No reads or edits of secret files: `.env` files, `auth.json`, key and
   token files, `~/.ssh`.
3. No force-push in any form, and no push to `main` or `master`.
4. No `gh pr merge` without `--match-head-commit`. Builders never merge; gate
   threads keep the pinned merge under Shyam's standing auto-merge rule.

Pushing a task branch stays allowed, because builder PRs depend on it. The
list only denies: nothing here allows anything, and no entry widens a
permission. The coordinator's own guard
(`~/.pi/agent-coordinator/extensions/coordinator.ts`) is separate and not
touched.

## One source, installed into each enforcement point

`runtime/agents/deny-rules.json` is the single list.
`scripts/install_deny_rules.py` installs it:

| Tool | Enforcement point |
| --- | --- |
| Claude Code (`T3 claudeAgent` and Claude Code tabs) | `permissions.deny` in `~/.claude/settings.json`, the user settings the `claude` CLI reads |
| Claude Code, unpinned merge | `PreToolUse` Bash hook `~/.claude/hooks/deny-merge-guard.py`, registered in the same settings file; `permissions.deny` cannot express "deny unless `--match-head-commit`" |
| pi: `~/.pi/agent` (router), `agent-minimax`, `agent-glm`, `agent-deepseek`, `agent-openai-api`, `agent-anthropic-api` | `extensions/deny-guard.ts` in each directory, auto-discovered by pi, list embedded at install time |
| Prose scope files | the same list as a managed section in `runtime/pi/AGENTS.md` (committed; the installer refuses to run when it is missing), `~/.pi/agent-openai-api/AGENTS.md`, `~/.pi/agent-anthropic-api/AGENTS.md` and `~/.claude/CLAUDE.md` |

`runtime/pi/AGENTS.md` is the live scope file for the router, minimax, glm and
deepseek instances through symlinks, so it carries the section in the repo.
The installer skips any scope file that is a symlink.

## Install, status, uninstall

```sh
python3 scripts/install_deny_rules.py install
python3 scripts/install_deny_rules.py status
python3 scripts/install_deny_rules.py uninstall
```

Every edited file is backed up first to
`~/.local/state/mac-ops/deny-rules-backups/<timestamp>/`, and the receipt at
`~/.local/state/mac-ops/deny-rules-receipt.json` records exactly what install
added. Uninstall removes only those entries: Claude deny entries by value, the
hook registration by command, the installed guard files, and the managed
scope sections.

## Rollback

Revert the PR, then reinstall from the reverted checkout
(`python3 scripts/install_deny_rules.py install`) or run `uninstall`. The
backups taken on each run restore any file by hand if needed.

## Proof

`evidence/MO-530/probes.py` exercises each enforcement point on scratch data:
the installed guard files loaded the way pi loads them, the installed Claude
settings and hook on their real payloads, a scratch repo with a scratch bare
remote for the task-branch push, and a fake `.env` in a scratch folder for the
secret probes. It never reads a real secret and never pushes to a real remote.
