# tick.md change for Shyam's session (not made here)

File: `~/Code/coordinator/loop/tick.md`. After this PR merges and the lane job runs the new code, make two edits.

1. Lines 59 to 62 (the "Run `/opt/homebrew/bin/python3 loop/settle_dead.py --apply` once per tick" bullet). Replace the bullet with:

   - Dead threads settle in the lane pass (`recover_dead_runs`), not in the tick. Read the `DEAD` lines in `~/Library/Logs/coordinator/lanes.log` to see what it settled or flagged; a `coordinator needed` line is a real ask.

2. Line 19 ("... Do not start a new investigation or `settle_dead.py` after that point."). Drop " or `settle_dead.py`".

Then archive `loop/settle_dead.py` (move, do not delete). The installer drift check (MO ticket for `status`) lists it until it is gone.

Not carried over from the old script, by the ticket's scope: it also settled a thread with no ticket key after 2 hours and a thread with an off-board key after 12 hours. The lane driver flags those once instead.
