# Close checklist replay (MO-1077)

Two merged pull requests, run through the close checklist with
`python3 scripts/close_check_replay.py --pr 519 --pr 492` on 2026-11-18. The third case is
described after the run.

close check: shyamsivakumar/mac-ops#519 (merge 431d81f647b8)
scope: fail - outside the ticket's stated scope: coordinator/bin/hourly_selftest.py, coordinator/overnight/selftest.py
proof file: pass - evidence/MO-517/check-proof.md is present
checks: pass - every one of the 7 checks the proof file lists passed
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: FAIL shyamsivakumar/mac-ops#517
The work goes back to its builder and the ticket stays open.

close check: shyamsivakumar/mac-ops#492 (merge 13c79aedc6fa)
scope: pass - every changed file is inside the ticket's stated scope
proof file: fail - the pull request carries no proof file at evidence/MO-491/check-proof.md
checks: skipped - there is no proof file to read
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: FAIL shyamsivakumar/mac-ops#491
The work goes back to its builder and the ticket stays open.

## What each case shows

- #519 (Refs #517): the ticket names `lane_driver.py` and `herdr/*`, and the diff also
  touches coordinator/bin/hourly_selftest.py and coordinator/overnight/selftest.py, so the
  diff is outside the ticket's stated scope. Its proof file is present and all seven
  of its checks passed. The work goes back to its builder and the ticket stays open.
- #492 (Refs #491): the ticket names the files it changes, so the scope is inside the
  stated scope, but the pull request carries no proof file at
  evidence/MO-491/check-proof.md. The work goes back to its builder and the ticket stays
  open.
- **The passing case.** No merged pull request in this repository passes the tightened
  rule yet, and the replay says so rather than dressing it up: every mac-ops ticket
  describes its area in prose, so the ticket authorizes no file, so the scope cannot
  be judged and the close is refused. The checklist read every merged pull request in
  this repository to find that. The only ones that carry a proof file are #498 and
  #529 (MO-496), #510 (MO-501), #519 (MO-517) and #528 (MO-521), and each of their
  tickets names at most one file, so each of them fails the scope item. The passing
  path is proven by `tests/test_close_check.py`, which asserts that a checklist with
  no blocking item closes the ticket and reports `RESULT: PASS`.

## What this means for a ticket that names no file

The close is refused, and the refusal says why: the ticket has to name the files it
changes. MO-524's own ticket names no file, so this checklist refuses to close
MO-524 as well. Two ways out, and both are the coordinator's: name the files in the
ticket body, or close the ticket outside the checklist. The checklist never reads the
pull request body for the scope, so a pull request cannot widen the scope of the
ticket that asked for the change.
