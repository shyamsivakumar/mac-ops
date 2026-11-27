# MO-1332 proof runs (Refs #1080)

## Red on origin/main (906862ac): head proof.sh and head test file against main code
```
Traceback (most recent call last):
  File "<string>", line 1, in <module>
KeyError: 'push_personal'
ticket proof exit 1
ERROR: test_hook_constants_match_the_list (tests.test_install_deny_rules.ListTest)
FAIL: test_pushes_are_decided_from_the_command_destinations (tests.test_install_deny_rules.HookTest)
Ran 31 tests in 8.386s
FAILED (failures=1, errors=1)
```

## Green on head
```
deny ask
ticket proof exit 0
guard personal repo, push origin main: deny
guard other remote, push origin main: ask
guard unresolvable remote, push origin main: deny
guard personal repo, push origin work: allow
guard personal repo, force push: deny
--- new work branch
To <tmp>/remote.git
 * [new branch]      work -> work
exit 0
--- fast-forward work branch
To <tmp>/remote.git
   3ed2bb0..59fce73  work -> work
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
main still at 3ed2bb0424403fa9663661b0639365c40147dee3
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
Ran 31 tests in 11.342s
OK
```
