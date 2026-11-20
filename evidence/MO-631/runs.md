# MO-631 proof

Ticket has no proof command. Proof is a replay of the #626 change as paths, in the `stall` eval of `coordinator/overnight/selftest.py` (unstick-brief block), run directly with temp COORDQ_DIR and COORD_JOURNAL_DIR.

Before (origin/main code, new assertions copied in):

    AssertionError: expected 'hold', got 'clear'    # lane_briefs.py is not a prompt path, brief text sits in lane_driver.py

After (branch):

    ITEM SUMMARY failures=0
    stall PASS
