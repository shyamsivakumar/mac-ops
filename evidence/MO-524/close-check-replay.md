# Close checklist replay (MO-1077)

Three recent merged pull requests, run through the close checklist with
`python3 scripts/close_check_replay.py --pr 528 --pr 429 --pr 519` on 2026-11-18.

close check: shyamsivakumar/mac-ops#528 (merge 62676880acac)
scope: pass - every changed file is inside the ticket's stated scope
proof file: pass - evidence/MO-521/check-proof.md is present
checks: pass - every one of the 9 checks the proof file lists passed
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: PASS shyamsivakumar/mac-ops#521

close check: shyamsivakumar/mac-ops#429 (merge 580535a0b096)
scope: pass - every changed file is inside the ticket's stated scope
proof file: fail - the pull request carries no proof file at evidence/MO-428/check-proof.md
checks: skipped - there is no proof file to read
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: FAIL shyamsivakumar/mac-ops#428
The work goes back to its builder and the ticket stays open.

close check: shyamsivakumar/mac-ops#519 (merge 431d81f647b8)
scope: fail - outside the ticket's stated scope: coordinator/bin/hourly_selftest.py, coordinator/overnight/selftest.py
proof file: pass - evidence/MO-517/check-proof.md is present
checks: pass - every one of the 7 checks the proof file lists passed
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: FAIL shyamsivakumar/mac-ops#517
The work goes back to its builder and the ticket stays open.

## What each case shows

- #528 (Refs #521) passes every item. Its ticket names
  `coordinator/bin/gate_reviewers.py` in the behavior change, and says its existing
  tests may change, so `tests/test_gate_reviewer_quota.py` and
  `tests/test_gatekeep_retry_limit.py` are inside the scope the ticket states.
  The proof file is there and all nine of its checks passed.
- #429 (Refs #428) carries no proof file, so the work goes back to its builder and
  the ticket stays open. Its diff is inside the scope its ticket states.
- #519 (Refs #517) touches `coordinator/bin/hourly_selftest.py` and
  `coordinator/overnight/selftest.py`, which its ticket never names, so the diff is
  outside the scope the ticket states. The work goes back to its builder and the
  ticket stays open.

The cost note item is skipped in all three: MO-1068 (#504) is report only and
its report (evidence/MO-1068/cost-report.md) does not exist yet.

## The scope comes from the ticket alone

The pulls above state their scope in their own bodies, and none of it is read: a
pull request that declares a file the ticket never names does not put that file in
scope. A ticket that names no file of this repository leaves the scope unjudged,
and an unjudged scope stops the close.
