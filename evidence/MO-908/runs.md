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

## Review round 1 (coordinator): doubt and off-by-default fixes

Cases run singly with a temp COORDQ_DIR and COORD_JOURNAL_DIR (doubt case extended with a missing journal directory and an unterminated last line; new case for the mark written only when the switch is on, and a failed mark write logged with the exit code kept).

a4bb576e: FAIL test_doubt_runs_the_tick, FAIL test_the_mark_is_written_only_when_the_precheck_is_on_and_a_failed_write_keeps_the_exit (Ran 4, failures=2)

fix head: Ran 4 tests, OK

Ticket proof command, unchanged, on the fix head: exit 0.

Note: an existing journal directory with no month file in the window still skips, because the ticket's proof skips on its second run before any event was written. A missing directory runs the tick.
