# MO-960 runs

Temp COORD_INBOX_DIR and COORD_JOURNAL_DIR throughout. origin/main means 8774e10c code files copied out with git show; the branch selftest is run against them for the eval case.

```text
## Proof command, origin/main
AttributeError: module 'inbox_worker' has no attribute 'liveness'
## Proof command, branch
exit 0
## inbox eval, origin/main code with the branch selftest
    return w.liveness(**{**dict(now=1000.0, lock_held=True, heartbeat=900.0, last_pass_end=0.0, expect_passes=False), **k})
AttributeError: module 'inbox_worker' has no attribute 'liveness'
## inbox eval, branch in place
exit 0
## inbox eval, branch flat copy of bin and overnight
exit 0
```

Watchdog no-op: with COORD_INBOX_DIR pointing at a path that does not exist, lane_driver.inbox_liveness() returned None and the path was not created (exit 0). The existing watchdog eval passes (its open() mock is fed a patched inbox_liveness).
