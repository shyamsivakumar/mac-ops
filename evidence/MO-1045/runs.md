# MO-1045 proof runs

Command: `sh evidence/MO-1045/proof.sh` (`build_here` selftest, no live sends).

## origin/main lane_driver.py with the new case (red)

    AssertionError: expected False, got True
    (owned PR with a FAIL gate: the herdr-build-MO-21 card was raised)

## head (green)

    PASS build-here: owned PR: fix_skipped_owned, no card; unowned: card
    (summary line, shortened from the original output)

## Fixtures on head

Owned by a running builder thread, owned by a waiting builder thread, owned by an `Owner: t1j` line with a completed thread: no card, one fix_skipped_owned row, unchanged on a second tick. Unreadable thread status with no Owner line: card raised.
