# MO-900 runs

## Proof command, before (origin/main)
```
AssertionError: deepseek/deepseek-flash
exit 1
```

## Proof command, after (branch)
```
exit 0

coordinator/launchd/dev.coordinator.tick.plist: OK
```

## Test case, branch
`python3 -m unittest tests.test_install_coordinator` with temp COORDQ_DIR and COORD_JOURNAL_DIR: Ran 60 tests, OK. The renamed case asserts the new pin, so it fails on origin/main with the same AssertionError as the proof command.
