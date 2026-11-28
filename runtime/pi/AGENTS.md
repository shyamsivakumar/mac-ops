<!-- agents-index:v1 -->
# pi operating index

User-level rules for pi board workers, linked by mac-ops from
`~/.pi/agent/AGENTS.md`. Do not apply Codex or Claude worker routes here.

## Precedence and ownership

- This file, then `/Users/shyamsivakumar/Code/AGENTS.md`, then the repository `AGENTS.md`.
- Knowledge home: `/Users/shyamsivakumar/Code/llmwiki`.
- Shared skills: `runtime/codex/skills` (same tree omp and Codex use).
- Project overlays: `/Users/shyamsivakumar/Code/.agents/skills`.
- llmwiki is the lasting source; write durable lessons there.

## Safety and evidence

- Never expose credentials, tokens, private keys, or `.env` values.
- Ask before destructive or irreversible actions unless the task allows them.
- Heavy CPU or memory commands go through `~/.local/bin/heavy`, one at a
  time per task. Never bypass it or raise its thresholds.
- For web proof, use Herdr UI's browser
  (`/Applications/Herdr.app/Contents/MacOS/Herdr browser …`), not Chrome.
- In unattended work, never open question dialogs (`AskUserQuestion`,
  `request_user_input`). If blocked, write `closing-note.md` and run
  `herdr-projects report … --state blocked`.

## Board tasks

- Use `/Users/shyamsivakumar/.herdr-projects/data/bin/herdr-projects` for
  board commands. Load the `herdr-projects` skill for the full reference.
- Temp output goes in the task `$TMPDIR` from the brief, not `/tmp` or home.
- `worker.effort` maps to pi's `--thinking` level (`max` → `--thinking max`).
  There is no separate pi-only effort config.

## MCP and tools

- Primary MCP entry is Executor at `~/.pi/agent/mcp.json`. Reach xerj, exa,
  context7, Notion, and others through its `execute` tool unless a task
  names a direct server.
- Read skills from the shared catalog; in print mode, read the skill file
  path explicitly if slash invocation does not load the body.

## Verification

- Before claiming done, follow `verification-before-completion`: exercise
  the real path and record evidence in the closing note. Static checks
  alone are not proof.

<!-- BEGIN mac-ops deny-rules -->
## Machine-enforced deny rules (mac-ops #530)

A machine guard enforces this list before tools run; prose cannot override it.
The list lives in `mac-ops runtime/agents/deny-rules.json` and `scripts/install_deny_rules.py` installs it.

Asks the owner in an interactive thread (a headless run is denied):

- Reads or edits under `~/Code/slash-eureka` (the Ascend repos: AUH, MCP, OPS, DBT, OMN) from a session that did not start there.
- A push to `main` or `master` elsewhere (not a personal repo), and `gh pr merge` outside personal repos (it runs without asking in github.com/shyamsivakumar/*).
- Printing secret values with `gcloud secrets versions access`, `heroku config` or `config:get`, or a gcloud `--format` that shows one.

Denied even with approval:

- A push to `main` or `master` of a personal repo (github.com/shyamsivakumar/*), or whose remote cannot be resolved.
- Reading secret files or running commands on them: `.env` files, `auth.json`, key and token files, `~/.ssh`.
- Force-push in any form.
- Remote and cloud deletes: `gcloud ... delete`, `bq rm`, `heroku ... destroy`, `gh repo delete`, `gh release delete`, `git push --delete`.
- `git stash` in any form except `list` and `show`: the stash list is shared by every worktree of a repository.
- Removing secret files or anything under `~/Code/slash-eureka`.
<!-- mac-ops deny-rules END -->

For omp conventions, see `llmwiki/runtime/omp/AGENTS.md`. Pi board workers
follow this file instead.
