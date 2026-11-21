# MO-768 proof runs

## Before: origin/main (f8a83246), no proof_run.py
```
/Applications/Xcode.app/Contents/Developer/usr/bin/python3: can't open file '/private/tmp/mo768-base/coordinator/bin/proof_run.py': [Errno 2] No such file or directory
exit 2
/Applications/Xcode.app/Contents/Developer/usr/bin/python3: can't open file '/private/tmp/mo768-base/coordinator/bin/proof_run.py': [Errno 2] No such file or directory
exit 2
```

## After: branch worktree
```
{"state": "red", "exit": 1, "matched": true, "ref": "78e40653413144fbacba7da1f72c80de7af9ae6e"}
exit 0
{"state": "green", "exit": 0, "matched": null, "ref": "78e40653413144fbacba7da1f72c80de7af9ae6e"}
exit 0
```

## Record written by the runner (--record)
## Proof run: red 78e40653413144fbacba7da1f72c80de7af9ae6e

```sh
echo hi >&2; exit 3
```

```
hi

```

{"state": "red", "exit": 3, "matched": true, "ref": "78e40653413144fbacba7da1f72c80de7af9ae6e"}

## parse_body on #794
```
 {'cmd': 'python3 -m unittest tests.test_gate_reviewer_quota.ReviewerQuotaTests.test_vendor_routing', 'expected_main': 'FAILED (failures=1), the codex vs openai-api assertion', 'expected_head': 'OK'} 
```

## parse_body on #768
```
 {'cmd': 'python3 coordinator/bin/proof_run.py red --repo-dir . --ref origin/main --cmd \'test -f no-such-file-x\' --signature \'.*\'; echo "exit $?"\npython3 coordinator/bin/proof_run.py green --repo-dir . --ref origin/main --cmd \'test -f README.md\'; echo "exit $?"', 'expected_main': None, 'expected_head': None} 
```
