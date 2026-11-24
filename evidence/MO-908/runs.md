# MO-908 runs

Ticket proof command saved as a script; temp HOME, COORD_JOURNAL_DIR, COORD_TICK_LOG, COORD_TICK_LOCK and COORD_TICK_MARK.

## origin/main (red)
```
  File "<string>", line 1, in <module>
AssertionError: skip
exit 1
```

## head (green)
```
exit 0
```

## New TestTickLauncher cases run singly (temp COORDQ_DIR, COORD_JOURNAL_DIR)

origin/main: AttributeError: module 'coord_tick' has no attribute 'skip_reason' (3 errors)

head: Ran 3 tests, OK
