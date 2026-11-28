# MO-1332 proof runs (Refs #1138)

## Red on origin/main (906862ac): head proof.sh and head test file against main code
```
Traceback (most recent call last):
  File "<string>", line 1, in <module>
KeyError: 'push_personal'
ticket proof exit 1
ERROR: test_hook_constants_match_the_list (tests.test_install_deny_rules.ListTest)
FAIL: test_pushes_are_decided_from_the_command_destinations (tests.test_install_deny_rules.HookTest)
Ran 31 tests in 8.116s
FAILED (failures=1, errors=1)
```

## Red for the two gate findings: previous head guard (8cc45530) on the new cases
```
guard ssh url with a port, push origin main: ask
guard external push url first, personal second, push origin main: ask
```

## Green on head
```
deny ask
ticket proof exit 0
guard personal repo, push origin main: deny
guard other remote, push origin main: ask
guard unresolvable remote, push origin main: deny
guard ssh url with a port, push origin main: deny
guard external push url first, personal second, push origin main: deny
guard personal repo, push origin work: allow
guard personal repo, force push: deny
--- new work branch
To <tmp>/remote.git
 * [new branch]      work -> work
exit 0
--- fast-forward work branch
To <tmp>/remote.git
   b4bdfa4..5361d58  work -> work
exit 0
--- push to main
pre-push refused: pushes to main are blocked; push a work branch
error: failed to push some refs to '<tmp>/remote.git'
exit 1
--- push to master
pre-push refused: pushes to master are blocked; push a work branch
error: failed to push some refs to '<tmp>/remote.git'
exit 1
--- delete main
pre-push refused: pushes to main are blocked; push a work branch
error: failed to push some refs to '<tmp>/remote.git'
exit 1
main still at b4bdfa40d107c95adbc8a5e96ee9768c5d17cf34
--- force push work branch
pre-push refused: refs/heads/work is not a fast-forward (force push or git error)
error: failed to push some refs to '<tmp>/remote.git'
exit 1
--- force-with-lease work branch
pre-push refused: refs/heads/work is not a fast-forward (force push or git error)
error: failed to push some refs to '<tmp>/remote.git'
exit 1
--- delete work branch
To <tmp>/remote.git
 - [deleted]         work
exit 0
--- new branch after refusals
To <tmp>/remote.git
 * [new branch]      work -> work2
exit 0
--- remote refs
refs/heads/main
refs/heads/work2
Ran 31 tests in 11.188s
OK
```
