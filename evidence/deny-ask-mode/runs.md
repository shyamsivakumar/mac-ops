# Deny rules ask mode: proof runs

Run on 2026-11-20 from the deny-ask-mode worktree. Nothing under the real ~/.claude, ~/.pi or settings was written.

## Hook decisions, before and after

Before is the installed ~/.claude/hooks/deny-merge-guard.py. After is the repo hook, run with HOME pointed at a temp dir so the audit log stays out of the real state dir, and with CLAUDE_PROJECT_DIR set only where the project dir column shows one. The permission_mode column is sent in the payload; the installed guard ignores it. The before column covers the hook only: Claude Code settings entries (Read, Edit and some Bash patterns in permissions.deny) also applied before and are covered in the installer section.

| command | project dir | permission_mode | before | after |
| --- | --- | --- | --- | --- |
| `gh pr merge 531 --squash` | - | default | deny | ask |
| `gh pr merge 531 --squash` | - | auto | deny | ask |
| `gh pr merge 531 --squash` | - | bypassPermissions | deny | deny |
| `gh pr merge 531 --squash` | - | dontAsk | deny | deny |
| `gh pr merge 531 --squash` | - | brandNewMode | deny | deny |
| `git push origin main` | - | default | deny | ask |
| `git push origin HEAD:master` | - | default | deny | ask |
| `cat app/.env` | - | default | allow | ask |
| `cat ~/.ssh/id_rsa` | - | default | allow | ask |
| `ls ~/.ssh` | - | default | allow | allow |
| `gcloud run services list` | - | default | allow | allow |
| `gcloud run deploy svc --image x` | - | default | allow | allow |
| `bq query 'select 1'` | - | default | allow | allow |
| `heroku logs -a x` | - | default | allow | allow |
| `heroku config:set A=1 -a x` | - | default | allow | allow |
| `gcloud secrets versions access latest --secret=api` | - | default | allow | ask |
| `gcloud run services describe s --format='value(payload)'` | - | default | allow | ask |
| `heroku config -a x` | - | default | allow | ask |
| `heroku config:get KEY -a x` | - | default | allow | ask |
| `cat ~/Code/slash-eureka/README.md` | - | default | allow | ask |
| `cd ~/Code/slash-eureka/x && ls` | - | default | deny | ask |
| `ls (cwd ~/Code/slash-eureka/x)` | - | default | deny | ask |
| `echo hi (cwd ~/Code/slash-eureka/x)` | ~/Code/slash-eureka | default | deny | allow |
| `git status (cwd ~/Code/slash-eureka/x)` | ~/Code/slash-eureka | default | deny | allow |
| `cd ~/Code/slash-eureka/x && git status` | ~/Code/slash-eureka | default | deny | allow |
| `cat app/.env (cwd ~/Code/slash-eureka/x)` | ~/Code/slash-eureka | default | deny | ask |
| `rm ~/Code/slash-eureka/x (cwd ~/Code/slash-eureka/x)` | ~/Code/slash-eureka | default | deny | allow |
| `git push origin t3/x --force` | - | default | deny | deny |
| `git push -f origin t3/x` | - | default | deny | deny |
| `git push --force-with-lease origin t3/x` | - | default | deny | deny |
| `git push --force-with-lease=t3/x origin t3/x` | - | default | deny | deny |
| `git push origin +t3/x` | - | default | deny | deny |
| `git push origin main --force` | - | bypassPermissions | deny | deny |
| `Read ~/Code/slash-eureka/src/a.py (cwd ~/Code/mac-ops)` | ~/Code/slash-eureka | default | deny (settings) | allow |
| `Edit ~/Code/slash-eureka/src/a.py (cwd ~/Code/mac-ops)` | ~/Code/slash-eureka | default | deny (settings) | allow |
| `Grep x in ~/Code/slash-eureka (cwd ~/Code/mac-ops)` | ~/Code/slash-eureka | default | allow | allow |
| `Read ~/Code/slash-eureka/src/a.py (cwd ~/Code/mac-ops)` | - | default | deny (settings) | ask |
| `Edit ~/Code/slash-eureka/src/a.py (cwd ~/Code/mac-ops)` | - | default | deny (settings) | ask |
| `Grep x in ~/Code/slash-eureka (cwd ~/Code/mac-ops)` | - | default | allow | ask |
| `Glob ~/Code/slash-eureka/**/*.py (cwd ~/Code/mac-ops)` | - | default | allow | ask |
| `Read ~/link/src/a.py (symlink into slash-eureka) (cwd ~/Code/mac-ops)` | - | default | allow | ask |
| `Write ~/link/new.py (symlink into slash-eureka) (cwd ~/Code/mac-ops)` | - | default | allow | ask |
| `Read ~/Code/mac-ops/README.md (cwd ~/Code/mac-ops)` | - | default | allow | allow |
| `git push --delete origin t3/x` | - | default | allow | deny |
| `git push -d origin t3/x` | - | default | allow | deny |
| `git push origin :t3/x` | - | default | allow | deny |
| `gcloud compute instances delete vm1 --quiet` | - | default | allow | deny |
| `bq rm -t ds.tbl` | - | default | allow | deny |
| `heroku apps:destroy -a x --confirm x` | - | default | allow | deny |
| `heroku addons:destroy db -a x` | - | default | allow | deny |
| `gh repo delete a/b --yes` | - | default | allow | deny |
| `gh release delete v1 --yes` | - | default | allow | deny |
| `gh api -X DELETE repos/a/b/git/refs/heads/x` | - | default | allow | deny |
| `gh api --method DELETE repos/a/b` | - | default | allow | deny |
| `curl -X DELETE https://x.test/a` | - | default | allow | deny |
| `curl --request DELETE https://x.test/a` | - | default | allow | deny |
| `http DELETE https://x.test/a` | - | default | allow | deny |
| `gh api repos/a/b` | - | default | allow | allow |
| `curl https://x.test/a` | - | default | allow | allow |
| `rm app/.env` | - | default | allow | deny |
| `rm -rf ~/Code/slash-eureka/x` | - | default | allow | deny |
| `rmdir ~/Code/slash-eureka/x` | - | default | allow | deny |
| `unlink ~/.ssh/id_rsa` | - | default | allow | deny |
| `trash cert.pem` | - | default | allow | deny |
| `find ~/Code/slash-eureka -name x -delete` | - | default | allow | deny |
| `rm -rf build` | - | default | allow | allow |
| `git push -u origin t3/x` | - | default | allow | allow |
| `git status` | - | default | allow | allow |
| `echo hi` | - | default | allow | allow |

Guard error (fail closed): a payload whose cwd is not a string makes classification raise for a command that names gh.

```
{"tool_name":"Bash","tool_input":{"command":"gh pr view 1"},"cwd":123}
```

```
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "mac-ops deny rules (#530): guard error: the command could not be classified, so it is denied"}}
```

The same command with a valid cwd is allowed, and a failing classification of a command that names no guarded tool (echo hi) is allowed.

A full ask reason, as Claude Code shows it:

```
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": "mac-ops deny rules (#530): [merge] gh pr merge needs the owner's approval; merges belong to the lane and the merge pass (approve it to run the command)\ncommand: gh pr merge 531 --squash\ncwd: /tmp/work"}}
```

Audit log lines from this table run (command cut to 200 chars, secret paths redacted):

```
{"time": "2026-11-20T16:57:03Z", "runtime": "claude", "session_id": "probe", "family": "secret_files", "decision": "ask", "command": "cat [secret]"}
{"time": "2026-11-20T16:57:03Z", "runtime": "claude", "session_id": "probe", "family": "cloud_secret", "decision": "ask", "command": "gcloud run services describe s --format='value(payload)'"}
{"time": "2026-11-20T16:57:03Z", "runtime": "claude", "session_id": "probe", "family": "secret_files", "decision": "ask", "command": "cat [secret]"}
{"time": "2026-11-20T16:57:04Z", "runtime": "claude", "session_id": "probe", "family": "force_push", "decision": "deny", "command": "git push --force-with-lease origin t3/x"}
{"time": "2026-11-20T16:57:04Z", "runtime": "claude", "session_id": "probe", "family": "force_push", "decision": "deny", "command": "git push origin main --force"}
```

## pi guard

The installed guard (from the installer run below) loaded in bun, tool_call handler called with a stub ctx. Confirm calls is how many times ctx.ui.confirm ran.

| case | ctx.mode | confirm calls | result | reason |
| --- | --- | --- | --- | --- |
| tui, confirm true: gh pr merge 531 | tui | 1 | RUN |  |
| tui, confirm false: gh pr merge 531 | tui | 1 | BLOCK | [merge] gh pr merge needs the owner's approval; merges belong to the l |
| rpc: gh pr merge 531 | rpc | 0 | BLOCK | [merge] gh pr merge needs the owner's approval; merges belong to the l |
| print: git push origin main | print | 0 | BLOCK | [push_protected] pushing to main or master needs the owner's approval; |
| json: cat app/.env | json | 0 | BLOCK | [secret_files] commands on secret files (.env, auth.json, keys, tokens |
| tui, confirm true: cat app/.env | tui | 1 | RUN |  |
| tui, confirm true: read tool on a fake .env | tui | 1 | RUN |  |
| tui, confirm true: edit tool on a fake .env | tui | 0 | BLOCK | secret file: /tmp/fake/app/.env. This is machine-enforced; route the w |
| tui, confirm true: heroku config -a x | tui | 1 | RUN |  |
| tui, confirm true: git push --delete origin t3/x (hard) | tui | 0 | BLOCK | [remote_delete] remote and cloud deletes are denied (denied even with  |
| tui, confirm true: curl -X DELETE (hard) | tui | 0 | BLOCK | [remote_delete] remote and cloud deletes are denied (denied even with  |
| tui, confirm true: rm app/.env (hard) | tui | 0 | BLOCK | [protected_removal] removing secret files or anything under ~/Code/sla |
| tui: gcloud run deploy (no prompt) | tui | 0 | RUN |  |
| tui: echo hi (no prompt) | tui | 0 | RUN |  |

## Installer against a temp copy of the home

The temp root starts from a copy of ~/.claude/settings.json with its deny list and deny hook removed, then the previous installer (origin/main) is run into it, so the starting state and the receipt are what a real upgrade sees. The new installer then upgrades it. Paths below are shortened from the temp root to `<root>`.

Dry run:

```
{'deny_entries': [78, 24], 'ask_entries': [0, 22], 'ascend_entries_left': []} (entry counts are [before, after])
dict_values(['changed']) ['changed', 'changed', 'changed', 'changed', 'changed', 'changed']
```

Install summary:

```
{
  "owner": "mac-ops/deny-rules.v1",
  "actions": [
    "claude settings: +24 deny entries, +22 ask entries, 0 existing deny entries moved to ask or retired",
    "claude hook: registered=True",
    "pi guard: <root>/.pi/agent/extensions/deny-guard.ts",
    "pi guard: <root>/.pi/agent-minimax/extensions/deny-guard.ts",
    "pi guard: <root>/.pi/agent-glm/extensions/deny-guard.ts",
    "pi guard: <root>/.pi/agent-deepseek/extensions/deny-guard.ts",
    "pi guard: <root>/.pi/agent-openai-api/extensions/deny-guard.ts",
    "pi guard: <root>/.pi/agent-anthropic-api/extensions/deny-guard.ts",
    "scope <root>/.pi/agent-openai-api/AGENTS.md: installed",
    "scope <root>/.pi/agent-anthropic-api/AGENTS.md: installed",
    "scope <root>/.claude/CLAUDE.md: installed"
```

Permissions before and after, and untouched keys:

```
before: {'allow': 2, 'deny': 78}
after:  {'allow': 2, 'deny': 24, 'ask': 22}
first ask entries: ['Read(~/.ssh/**)', 'Read(//private/tmp/claude-501/-Users-shyamsivakumar-Code/c283b00e-e8c8-422f-9aa1-eb7c969bb5ce/scratchpad/final.kRJG/.ssh/**)']
push-to-main entries now in ask: ['Bash(git push origin main:*)', 'Bash(git push origin master:*)']
force-push entries still in deny: ['Bash(git push --force:*)', 'Bash(git push -f:*)', 'Bash(git push --force-with-lease:*)']
slash-eureka entries left in deny or ask: []
slash-eureka entries before: 32
hook entries: [('Bash|Read|Edit|Write|MultiEdit|NotebookEdit|Grep|Glob', 'python3 <root>/.claude/hooks/deny-merge-guard.py')]
Edit(secret) still in deny: True
keys changed outside permissions and hooks: []
hook registered: ['python3 <root>/.claude/hooks/deny-merge-guard.py']
```

Backups written before the change (settings, previous hook):

```
<root>/.local/state/mac-ops/deny-rules-backups/<stamp>/snapshot/.claude/settings.json
<root>/.local/state/mac-ops/deny-rules-backups/<stamp>/snapshot/.local/state/mac-ops/deny-rules-receipt.json
<root>/.local/state/mac-ops/deny-rules-backups/<stamp>/snapshot/.claude/settings.json
<root>/.local/state/mac-ops/deny-rules-backups/<stamp>/snapshot/.claude/hooks/deny-merge-guard.py
<root>/.local/state/mac-ops/deny-rules-backups/<stamp>/snapshot/.claude/CLAUDE.md
<root>/.local/state/mac-ops/deny-rules-backups/<stamp>/snapshot/.pi/agent-openai-api/extensions/deny-guard.ts
<root>/.local/state/mac-ops/deny-rules-backups/<stamp>/snapshot/.pi/agent-openai-api/AGENTS.md
<root>/.local/state/mac-ops/deny-rules-backups/<stamp>/snapshot/.pi/agent-deepseek/extensions/deny-guard.ts
<root>/.local/state/mac-ops/deny-rules-backups/<stamp>/snapshot/.pi/agent-glm/extensions/deny-guard.ts
<root>/.local/state/mac-ops/deny-rules-backups/<stamp>/snapshot/.pi/agent/extensions/deny-guard.ts
<root>/.local/state/mac-ops/deny-rules-backups/<stamp>/snapshot/.pi/agent-anthropic-api/extensions/deny-guard.ts
<root>/.local/state/mac-ops/deny-rules-backups/<stamp>/snapshot/.pi/agent-anthropic-api/AGENTS.md
<root>/.local/state/mac-ops/deny-rules-backups/<stamp>/snapshot/.pi/agent-minimax/extensions/deny-guard.ts
```

Status after install:

```
{'installed': True, 'claude_deny_missing': [], 'claude_ask_missing': [], 'claude_ask_still_denied': [], 'claude_ascend_entries_present': [], 'merge_hook_file': True, 'pi_guards': ['installed']}
```

## Existing tests

```
.............................
----------------------------------------------------------------------
Ran 29 tests in 7.558s

OK
```
