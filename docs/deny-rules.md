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
   token files (`*token*.json`, `.txt`, `.yaml`, `.yml`), `~/.ssh`.
3. No force-push in any form, and no push to `main` or `master` on any
   remote. Task-branch pushes stay allowed, including a task branch whose
   name continues a protected one (`main.fix`, `main/fix`), and including a
   push whose *source* is a protected ref while its destination is a task
   branch (`main:task-530`). The rule compares the destination of each
   refspec, never its source, and it reads only a real `git push` command
   (including one behind `heavy`, `timeout`, `bash -c` or `eval`). A protected
   branch name anywhere else in the command text, such as a PR body, an `hc`
   message, a commit message or a heredoc, is not a push to it. The same
   command-position rule applies to the merge command. A push with no
   refspec (`git push`, `git push origin`, `git push origin HEAD`) writes the
   checked-out branch and the upstream branch it tracks, so the guards read
   both from the command's directory and refuse the push when either is
   protected or cannot be resolved (detached HEAD, `--git-dir`, or a `cd`
   earlier in the command). `--all`, `--mirror`, `:` and wildcard refspecs are
   refused because they can write `main`. `gh` global options such as
   `-R owner/repo` are skipped before the merge rule reads the subcommand.
4. No `gh pr merge` for a builder. Only a gate thread merges, and only with
   the pinned `--match-head-commit` head given as a merge argument.

Pushing a task branch stays allowed, because builder PRs depend on it. The
list only denies: nothing here allows anything, and no entry widens a
permission. The coordinator's own guard
(`~/.pi/agent-coordinator/extensions/coordinator.ts`) is separate and not
touched.

## The gate role

A pinned merge is not permission by wording. The guard allows it only when
both hold:

- **The caller is a gate.** The role is read from the environment the agent
  was launched with (`MAC_OPS_ROLE=gate`), never from the command. A command
  that mentions the role, or a builder that types the flag, grants nothing.
- **The pin is a merge argument.** A commit id (`--match-head-commit <sha>`, 40
  or 64 hex characters) must be the next word of the same `gh pr merge`
  invocation, read with the shell's quoting: a flag and id written inside a
  quoted multiword argument (a PR subject, a body) stay that argument's text
  and are not a pin. A missing value or a branch name is not a pin either, and
  the merge is refused.

A gate thread therefore needs `MAC_OPS_ROLE=gate` in the environment it is
launched with. T3 sets a thread's environment from its provider instance, and
the thread-launch input has no environment field of its own, so the role is
carried by a dedicated instance: `claudeAgentGate`, a `claudeAgent` entry whose
`environment` holds `MAC_OPS_ROLE=gate`.

That instance is part of the install, not a hand edit. `scripts/install_deny_rules.py
install` writes it into `~/.t3/userdata/settings.json` next to the hook
registration, `status` reports it, and `uninstall` removes it.

No launcher selects that instance in this change. The launcher that starts a
gate on `claudeAgentGate` is part 2 of #534 (`coordinator/overnight/`). Until
it lands, no thread holds the gate role and every agent-typed merge is
refused, which is the tighter outcome.

The role cannot be claimed by typing either. The hook refuses a thread launch,
thread send or batch thread creation whose input names `claudeAgentGate` from a
caller without the role, so a builder cannot hand itself the role by launching
a child on that instance, and no file or transcript token is read anywhere.

## One source, installed into each enforcement point

`runtime/agents/deny-rules.json` is the single list.
`scripts/install_deny_rules.py` installs it:

| Tool | Enforcement point |
| --- | --- |
| Claude Code (`T3 claudeAgent` and Claude Code tabs) | `permissions.deny` in `~/.claude/settings.json`, the user settings the `claude` CLI reads |
| Claude Code, merge role and remote-any push | `PreToolUse` Bash hook `~/.claude/hooks/deny-merge-guard.py`, registered in the same settings file; `permissions.deny` matches command prefixes, so it can express neither "unless the caller is a gate with a pinned argument" nor "on any remote" |
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
added. Uninstall removes only those entries: the Claude deny entries install
added (entries that were already there stay), the hook registration if install
added it, and the managed scope sections. A hook file, pi guard file or
`claudeAgentGate` instance that existed before install is restored from its
backup, and one that did not exist is removed.

## Rollback

Revert the PR, then reinstall from the reverted checkout
(`python3 scripts/install_deny_rules.py install`) or run `uninstall`. The
backups taken on each run restore any file by hand if needed.

## Proof

`evidence/MO-530/probes.py` exercises each enforcement point on scratch data:
the installed guard files loaded the way pi loads them, the installed Claude
hook on its real payload, a scratch repo with a scratch bare remote for the
task-branch push, and a fake `.env` in a scratch folder for the secret probes.
It never reads a real secret and never pushes to a real remote.

`permissions.deny` is evaluated by Claude Code inside a session, so those rows
are reported `not run` with the check to make; reading the settings file back
only proves an entry was written, not that a call is refused.
