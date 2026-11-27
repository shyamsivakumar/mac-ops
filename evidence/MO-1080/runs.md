# MO-1332 proof runs (Refs #1080)

## Red on origin/main (906862ac), head test file against main code
```
ask
ticket proof python exit 1
hook present exit 1
...........F.........F.........
======================================================================
FAIL: test_pushes_are_decided_from_the_command_destinations (tests.test_install_deny_rules.HookTest)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/private/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmp.2nPz1FTU5S/main/tests/test_install_deny_rules.py", line 488, in test_pushes_are_decided_from_the_command_destinations
    self.assertEqual(self.decided(command)["permissionDecision"], "deny", command)
AssertionError: 'ask' != 'deny'
- ask
+ deny
 : git push origin main

======================================================================
FAIL: test_install_writes_every_enforcement_point (tests.test_install_deny_rules.InstallTest)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/private/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmp.2nPz1FTU5S/main/tests/test_install_deny_rules.py", line 84, in test_install_writes_every_enforcement_point
    self.assertIn("Bash(git push origin main:*)", rules["deny"])
AssertionError: 'Bash(git push origin main:*)' not found in ['Edit(~/.ssh/**)', 'Edit(//var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/deny-rules-test-2yw0c6mk/.ssh/**)', 'Edit(**/.env)', 'Edit(**/.env.*)', 'Edit(**/auth.json)', 'Edit(**/*.pem)', 'Edit(**/*.key)', 'Edit(**/id_rsa*)', 'Edit(**/id_dsa*)', 'Edit(**/id_ed25519*)', 'Edit(**/id_ecdsa*)', 'Edit(**/credentials)', 'Edit(**/credentials.json)', 'Edit(**/.netrc)', 'Edit(**/.npmrc)', 'Edit(**/.pypirc)', 'Edit(**/*token*.json)', 'Edit(**/*token*.txt)', 'Edit(**/*token*.yaml)', 'Edit(**/*token*.yml)', 'Bash(git push --force:*)', 'Bash(git push -f:*)', 'Bash(git push --force-with-lease:*)', 'Bash(git push --force-if-includes:*)']

----------------------------------------------------------------------
Ran 31 tests in 8.633s

FAILED (failures=2)
```

## Green on head
```
----------------------------------------------------------------------
Ran 31 tests in 10.622s

OK
```

## Ticket proof and bare-repo pushes on the head

```
deny
ticket proof exit 0
--- new work branch
To <tmp>/remote.git
 * [new branch]      work -> work
exit 0
--- fast-forward work branch
To <tmp>/remote.git
   8e670bf..9c2a56b  work -> work
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
main still at 8e670bfbde35511bfb6089b97f66d2b2c9c0b154
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
```
