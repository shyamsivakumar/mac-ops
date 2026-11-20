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
| `rm "~/Code/slash-eureka/a b/x"` | - | default | allow | deny |
| `rm ~/Code/slash-eureka/a\ b/x` | - | default | allow | deny |
| `rm 'my dir/.env'` | - | default | allow | deny |
| `rm my\ dir/.env` | - | default | allow | deny |
| `unlink ~/.ssh/my\ key.pem` | - | default | allow | deny |
| `find "~/Code/slash-eureka/a b" -delete` | - | default | allow | deny |
| `trash "a b/.env"` | - | default | allow | deny |
| `cat "~/Code/slash-eureka/a b/x"` | - | default | allow | ask |
| `rm "my docs/notes.txt"` | - | default | allow | allow |
| `curl -u user:pass -X DELETE https://x.test/a` | - | default | allow | deny |
| `curl -X DELETE https://user:pass@x.test/a` | - | default | allow | deny |
| `git push https://tok@github.com/a/b.git main` | - | default | deny | ask |
| `rm ~/.ssh/id_* (cwd ~/work)` | - | default | allow | deny |
| `rm ~/.ssh/* (cwd ~/work)` | - | default | allow | deny |
| `rm ~/.ssh/nothing_* (cwd ~/work)` | - | default | allow | deny |
| `rm *.pem (cwd ~/keys)` | - | default | allow | deny |
| `rm .en? (cwd ~/keys)` | - | default | allow | deny |
| `rm {a,x}.pem (cwd ~/keys)` | - | default | allow | deny |
| `find ~/.ssh -name 'id_*' -delete (cwd ~/work)` | - | default | allow | deny |
| `find . -name '*.log' -delete (cwd ~/keys)` | - | default | allow | deny |
| `rm ~/Code/slash-eureka/*/x (cwd ~/work)` | - | default | allow | deny |
| `git rm .env (cwd ~/keys)` | - | default | allow | deny |
| `ls \| xargs rm x.pem (cwd ~/keys)` | - | default | allow | deny |
| `rm build/*.o (cwd ~/work)` | - | default | allow | allow |
| `rm *.log (cwd ~/work)` | - | default | allow | allow |
| `find build -name '*.o' -delete (cwd ~/work)` | - | default | allow | allow |
| `git rm a.log (cwd ~/work)` | - | default | allow | allow |
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
{"time": "2026-11-20T21:37:00Z", "runtime": "claude", "session_id": "probe", "tool": "Bash", "family": "secret_files", "decision": "ask", "program": "cat"}
{"time": "2026-11-20T21:37:00Z", "runtime": "claude", "session_id": "probe", "tool": "Bash", "family": "cloud_secret", "decision": "ask", "program": "gcloud"}
{"time": "2026-11-20T21:37:00Z", "runtime": "claude", "session_id": "probe", "tool": "Bash", "family": "secret_files", "decision": "ask", "program": "cat"}
{"time": "2026-11-20T21:37:00Z", "runtime": "claude", "session_id": "probe", "tool": "Bash", "family": "force_push", "decision": "deny", "program": "git"}
{"time": "2026-11-20T21:37:01Z", "runtime": "claude", "session_id": "probe", "tool": "Bash", "family": "force_push", "decision": "deny", "program": "git"}
```

## Audit log redaction

Temp HOME /private/tmp/claude-501/-Users-shyamsivakumar-Code/c283b00e-e8c8-422f-9aa1-eb7c969bb5ce/scratchpad/audithome.yOgC; nothing reaches the real audit log. An Edit into slash-eureka from a non-Ascend session with fake secret-looking text in `new_string`, `old_string`, `content` and `edits`, then Bash commands that carry fake credentials: an echo of a password into slash-eureka, curl with -u user:pass, a URL with user:pass@, a git push to a URL with a token, an env-assigned token, and a quoted spaced path. A Bash line holds only the program name.

```
Edit  -> ask
Bash echo password=hunter2 > ~/Code/slash-eureka/x -> ask
Bash curl -u user:pass -X DELETE https://x.test/a -> deny
Bash curl -X DELETE https://user:pass@x.test/a -> deny
Bash git push https://tok@github.com/a/b.git main -> ask
Bash TOKEN=hunter2 cat ~/Code/slash-eureka/x -> ask
Bash rm "~/Code/slash-eureka/a b/x" --note=pw-hunter2 -> deny
Bash KEY="secret value here" curl -X DELETE https://x.test/a -> deny
Bash KEY="line one
secret line two" gh pr merge 1 -> ask
Bash env A='x y secret' gh pr merge 1 -> ask
Bash KEY=secret\ value\ here gh pr merge 1 -> ask
Bash 'odd prog name' x && gh pr merge 1 -> ask
```

Audit lines written:

```
{"time": "2026-11-20T21:37:07Z", "runtime": "claude", "session_id": "redact-demo", "tool": "Edit", "family": "ascend", "decision": "ask", "target": "<home>/Code/slash-eureka/app.py"}
{"time": "2026-11-20T21:37:07Z", "runtime": "claude", "session_id": "redact-demo", "tool": "Bash", "family": "ascend", "decision": "ask", "program": "echo"}
{"time": "2026-11-20T21:37:07Z", "runtime": "claude", "session_id": "redact-demo", "tool": "Bash", "family": "remote_delete", "decision": "deny", "program": "curl"}
{"time": "2026-11-20T21:37:07Z", "runtime": "claude", "session_id": "redact-demo", "tool": "Bash", "family": "remote_delete", "decision": "deny", "program": "curl"}
{"time": "2026-11-20T21:37:07Z", "runtime": "claude", "session_id": "redact-demo", "tool": "Bash", "family": "push_protected", "decision": "ask", "program": "git"}
{"time": "2026-11-20T21:37:08Z", "runtime": "claude", "session_id": "redact-demo", "tool": "Bash", "family": "ascend", "decision": "ask", "program": "cat"}
{"time": "2026-11-20T21:37:08Z", "runtime": "claude", "session_id": "redact-demo", "tool": "Bash", "family": "protected_removal", "decision": "deny", "program": "rm"}
{"time": "2026-11-20T21:37:08Z", "runtime": "claude", "session_id": "redact-demo", "tool": "Bash", "family": "remote_delete", "decision": "deny", "program": "curl"}
{"time": "2026-11-20T21:37:08Z", "runtime": "claude", "session_id": "redact-demo", "tool": "Bash", "family": "merge", "decision": "ask", "program": "gh"}
{"time": "2026-11-20T21:37:08Z", "runtime": "claude", "session_id": "redact-demo", "tool": "Bash", "family": "merge", "decision": "ask", "program": "gh"}
{"time": "2026-11-20T21:37:08Z", "runtime": "claude", "session_id": "redact-demo", "tool": "Bash", "family": "merge", "decision": "ask", "program": "gh"}
{"time": "2026-11-20T21:37:08Z", "runtime": "claude", "session_id": "redact-demo", "tool": "Bash", "family": "merge", "decision": "ask", "program": "unknown"}
```

Leak check over the whole audit file (each count must be 0):

```
secret value: 0
line two: 0
x y secret: 0
secret\ value: 0
odd prog: 0
hunter2: 0
user:pass: 0
tok@: 0
x.test: 0
AKIA: 0
OLD_SECRET_TEXT: 0
abc123: 0
sk-qqq: 0
new_string: 0
pw-: 0
"command": 0
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
| tui, confirm true: quoted env value with spaces, curl delete | tui | 0 | BLOCK | [remote_delete] remote and cloud deletes are denied (denied even with  |
| tui, confirm false: quoted env value with spaces, curl delete | tui | 0 | BLOCK | [remote_delete] remote and cloud deletes are denied (denied even with  |
| tui, confirm true: multi-line quoted env value, gh pr merge | tui | 1 | RUN |  |
| tui, confirm false: multi-line quoted env value, gh pr merge | tui | 1 | BLOCK | [merge] gh pr merge needs the owner's approval; merges belong to the l |
| tui, confirm true: env wrapper with quoted value, gh pr merge | tui | 1 | RUN |  |
| tui, confirm false: env wrapper with quoted value, gh pr merge | tui | 1 | BLOCK | [merge] gh pr merge needs the owner's approval; merges belong to the l |
| tui, confirm true: backslash-escaped env value, gh pr merge | tui | 1 | RUN |  |
| tui, confirm false: backslash-escaped env value, gh pr merge | tui | 1 | BLOCK | [merge] gh pr merge needs the owner's approval; merges belong to the l |
| tui, confirm true: odd program name, gh pr merge | tui | 1 | RUN |  |
| tui, confirm false: odd program name, gh pr merge | tui | 1 | BLOCK | [merge] gh pr merge needs the owner's approval; merges belong to the l |
| tui, confirm true: rm <root>/.ssh/id_* (hard) | tui | 0 | BLOCK | [protected_removal] removing secret files or anything under ~/Code/sla |
| tui, confirm true: rm *.pem in keys (hard) | tui | 0 | BLOCK | [protected_removal] removing secret files or anything under ~/Code/sla |
| tui, confirm true: rm .en? in keys (hard) | tui | 0 | BLOCK | [protected_removal] removing secret files or anything under ~/Code/sla |
| tui, confirm true: find . -name '*.log' -delete in keys (hard) | tui | 0 | BLOCK | [protected_removal] removing secret files or anything under ~/Code/sla |
| tui: rm build/*.o in work (no prompt) | tui | 0 | RUN |  |
| tui: rm *.log in work (no prompt) | tui | 0 | RUN |  |

Audit lines the pi guard wrote for the quoted-assignment cases (temp root, program field only; the secret text never appears):

```
   4 approved merge          gh
   1 approved merge          unknown
   9 ask      merge          gh
   2 ask      merge          unknown
   4 declined merge          gh
   1 declined merge          unknown
   3 deny     remote_delete  curl
```

```
secret value in pi audit lines: 0
line two in pi audit lines: 0
x y secret in pi audit lines: 0
secret\ value in pi audit lines: 0
odd prog in pi audit lines: 0
x.test in pi audit lines: 0
```

## Installer against a temp copy of the home

The temp root starts from a copy of ~/.claude/settings.json with its deny list and deny hook removed, then the previous installer (origin/main) is run into it, so the starting state and the receipt are what a real upgrade sees. The new installer then upgrades it. Paths below are shortened from the temp root to `<root>`.

Dry run:

```
{'deny_entries': [78, 24], 'ask_entries': [22, 23], 'ascend_entries_left': []} (entry counts are [before, after])
dict_values(['changed']) ['changed', 'changed', 'changed', 'changed', 'changed', 'changed']
```

Install summary:

```
{
  "owner": "mac-ops/deny-rules.v1",
  "actions": [
    "claude settings: +24 deny entries, +1 ask entries, 0 existing deny entries moved to ask or retired",
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
before: {'allow': 2, 'deny': 78, 'ask': 22}
after:  {'allow': 2, 'deny': 24, 'ask': 23}
first ask entries: ['Read(~/.ssh/**)', 'Read(//Users/shyamsivakumar/.ssh/**)']
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
<root>/.local/state/mac-ops/deny-rules-backups/<stamp>/snapshot/.claude/settings.json
```

Status after install:

```
{'installed': True, 'claude_deny_missing': [], 'claude_ask_missing': [], 'claude_ask_still_denied': [], 'claude_ascend_entries_present': [], 'merge_hook_file': True, 'pi_guards': ['installed']}
```

## Existing tests

```
..............................
----------------------------------------------------------------------
Ran 30 tests in 10.902s

OK
```
