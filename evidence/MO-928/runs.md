# MO-928 runs

## Ticket proof, origin/main (red)
```
AssertionError: None
```
## Ticket proof, branch (green)
```
exit 0
```

## Hook run, allow and deny (JSON fed on stdin from a file; old = origin/main hook, new = branch hook)

| command | before (origin/main) | after |
| --- | --- | --- |
| `git stash` | allow | deny |
| `git stash -q` | allow | deny |
| `git stash -u` | allow | deny |
| `git stash push -m x` | allow | deny |
| `git stash save` | allow | deny |
| `git stash pop` | allow | deny |
| `git stash apply stash@{1}` | allow | deny |
| `git stash drop` | allow | deny |
| `git stash clear` | allow | deny |
| `git stash branch b` | allow | deny |
| `git stash store` | allow | deny |
| `git stash create` | allow | deny |
| `git stash list` | allow | allow |
| `git stash show -p` | allow | allow |
| `git -C dir stash` | allow | deny |
| `git -c a=b stash pop` | allow | deny |
| `FOO=1 git stash` | allow | deny |
| `/usr/bin/git stash` | allow | deny |
| `cd x && git stash; make; git stash pop` | allow | deny |
| `bash -c 'git stash'` | allow | deny |
| `git commit -m 'avoid git stash here'` | allow | allow |
| `echo git stash` | allow | allow |
| `git log --grep stash` | allow | allow |

Unrelated commands, before and after:
- `git push origin main`: ask -> ask
- `git push --force origin t3/x`: deny -> deny
- `gh pr merge 1`: ask -> ask
- `git push origin t3/x`: allow -> allow
- `git status`: allow -> allow
- `git commit -m x`: allow -> allow
- `cat .env`: ask -> ask
- `rm -rf /tmp/zz`: allow -> allow
- `git log`: allow -> allow
- `git checkout x`: allow -> allow

Settings lists (claude_rules), before and after:
- ask: before 24, after 24, added [], removed []
- deny: before 24, after 24, added [], removed []
- retired: before 32, after 32, added [], removed []
family modes before: {'merge': 'ask', 'push_protected': 'ask', 'secret_files': 'ask', 'cloud_secret': 'ask', 'ascend': 'ask', 'force_push': 'deny', 'remote_delete': 'deny', 'protected_removal': 'deny', 'push_destination': 'deny'}
family modes after:  {'merge': 'ask', 'push_protected': 'ask', 'secret_files': 'ask', 'cloud_secret': 'ask', 'ascend': 'ask', 'force_push': 'deny', 'remote_delete': 'deny', 'protected_removal': 'deny', 'push_destination': 'deny', 'stash': 'deny'}

## Installer dry run against a temp root
```
{
  "dry_run": true,
  "claude_settings": {
    "deny_entries": [
      0,
      24
    ],
    "ask_entries": [
      0,
      24
    ],
    "ascend_entries_left": []
```

## Test case

tests.test_install_deny_rules.HookTest.test_git_stash_is_denied_except_list_and_show: fails against the origin/main hook (AssertionError: None != 'deny' : git stash), passes on the branch. Hook errors use the existing guard_error path (a deny when the command names git), unchanged.
