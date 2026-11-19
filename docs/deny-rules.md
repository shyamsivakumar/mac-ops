# Deny rules for agents

Machine-enforced deny list for agent permissions, approved by Shyam on
2026-11-17 (decisions board, "deny-rules": yes) and tracked as mac-ops #530.

Prose limits in `CLAUDE.md` and the scope files can be ignored by a model. A
deny rule blocks the tool before it runs, so the same list is installed where
each tool checks tools, and written into the scope files as prose.

## The list

1. No reads or edits under `~/Code/slash-eureka` (the Ascend repos).
2. No reads or edits of secret files: `.env` files, `auth.json`, key and token
   files, `~/.ssh`.
3. No force-push in any form, and no push to `main` or `master`.
4. No `gh pr merge` by an agent.
5. A command whose working directory is inside the Ascend tree is refused.

The list only denies. Nothing here allows anything.

`gh pr merge` is refused for every agent, in any role and with any arguments,
including `-R` or `--repo` before or after `pr`, and inside `bash -c`, `eval`
and the wrappers the push parser handles. The rule depends on #656 being
installed first: once it is, the lane and the merge pass (#647/#649) are
processes, not agents, so no agent merges anywhere. There is no gate role and
no pin check. A merge run from Shyam's own shell is not hooked and needs
nothing. A command parser cannot stop `gh api .../merge`, so that form is not
enforced here.

## How a push is decided

A push is decided only from the destinations written in the command. The
guards never ask git where a push would go.

- A push with no explicit destination refspec is refused: `git push`,
  `git push <remote>` alone, `HEAD` alone, `--all`, `--mirror`, `:`, wildcard
  refspecs, and a destination that is a shell expansion such as `$BRANCH`. The
  message tells the agent to name the branch, for example
  `git push -u origin <task-branch>`.
- An explicit refspec is judged by its destination: `<src>:<dst>`,
  `+<src>:<dst>`, `refs/heads/<dst>` or a plain `<branch>`. A destination of
  `main` or `master` is refused. A protected source with a task-branch
  destination (`main:task-530`) is allowed.
- Any force form is refused: `--force`, `-f`, `--force-with-lease`,
  `--force-if-includes`, and a `+` refspec.
- The first word after `push` (skipping options) is the repository. A remote
  named `main` is allowed when a task-branch refspec follows it.
- Only the shell's real commands count, including one behind `heavy`,
  `timeout`, `bash -c` or `eval`. A protected branch name in a PR body, an `hc`
  message, a commit message or a heredoc is text, not a push.

## Where each rule is installed

`runtime/agents/deny-rules.json` is the single list.
`scripts/install_deny_rules.py` installs it.

| Tool | Enforcement point |
| --- | --- |
| Claude Code | `permissions.deny` and `deny-merge-guard.py` hook |
| pi instances | `extensions/deny-guard.ts`, runs the same hook |
| Scope files | prose list in `runtime/pi/AGENTS.md`, `CLAUDE.md` |

## Install, status, uninstall

```sh
python3 scripts/install_deny_rules.py install
python3 scripts/install_deny_rules.py status
python3 scripts/install_deny_rules.py uninstall
```

`--root <dir>` installs under a scratch home instead of `~`.

A reinstall copies every file it can touch to
`~/.local/state/mac-ops/deny-rules-backups/<timestamp>/snapshot` before it
changes anything. If any step fails, the snapshot is put back, so a failed
reinstall never leaves fewer protections than the install it replaced. The
receipt records what install added and the prior content of each file it
replaced. Uninstall removes only those additions and restores the prior files,
hook and guards.

## Proof

`evidence/MO-530/probes.py` installs into a scratch home and probes the
installed Claude hook on its real payload and all six installed pi guards,
using a scratch repo and bare remote for the task-branch push. It never
touches the real `~/.claude`, `~/.local` or pi config. Claude evaluates
`permissions.deny` inside a session, so those rows are reported `not run`.
