# MO-1045 proof runs

Command: `sh evidence/MO-1045/proof.sh` (`build_here` selftest, no live sends).

## origin/main lane_driver.py with the new case (red)

    AssertionError: expected False, got True
    (owned PR with a FAIL gate: the herdr-build-MO-21 card was raised)

## head (green)

    PASS build-here: owned PR: fix_skipped_owned, no card; unowned: card
    (summary line, shortened from the original output)
