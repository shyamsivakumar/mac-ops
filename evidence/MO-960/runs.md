# MO-960 runs

Temp COORD_INBOX_DIR and COORD_JOURNAL_DIR throughout. Round 2 (review fixes), after merging origin/main 4375b7ab. origin/main means its code files copied out with git show; the branch selftest runs against them.

```text
## Proof command, origin/main
AttributeError: module 'inbox_worker' has no attribute 'liveness'
## Proof command, branch
exit 0
## inbox eval, origin/main code with the branch selftest
AttributeError: module 'inbox_worker' has no attribute 'liveness'
## inbox eval, previous head worker (6f500679) with the branch selftest
AssertionError: expected ([], [], True), got ([FileNotFoundError(2, 'No such file or directory') x50], [], True)
## inbox and watchdog evals, branch in place
exit 0
## inbox eval, branch flat copy of bin and overnight (flat copy has no pi/bin/coord-tick, so the watchdog eval cannot load there; it fails the same way for any code)
exit 0 for inbox (watchdog eval needs the repo layout; see heading)
```

Watchdog no-op: with COORD_INBOX_DIR pointing at a missing path, lane_driver.inbox_liveness() returns None and creates nothing (covered by the inbox eval). A PermissionError on the lock file yields the fixed-text alarm.
