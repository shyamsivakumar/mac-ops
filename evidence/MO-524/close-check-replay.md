# Close checklist replay (MO-1077)

Three recent merged pull requests, run through the close checklist with
`python3 scripts/close_check_replay.py --pr 529 --pr 429 --pr 519` on 2026-11-18.

close check: shyamsivakumar/mac-ops#529 (merge def2918d6cb8)
scope: pass - every changed file is inside the ticket's stated scope
proof file: pass - evidence/MO-496/check-proof.md is present
checks: pass - every one of the 6 checks the proof file lists passed
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: PASS shyamsivakumar/mac-ops#496

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

- #529 (Refs #496) passes every item: the diff stays inside the ticket's scope,
  the proof file is there and every check in it passed.
- #429 (Refs #428) has no proof file, so the work goes back to its builder and the
  ticket stays open. Its scope is inside the stated scope.
- #519 (Refs #517) touches coordinator/bin/hourly_selftest.py and
  coordinator/overnight/selftest.py, which its scope does not name, so the diff is
  outside the stated scope. The work goes back to its builder and the ticket stays
  open.

The cost note item is skipped in all three: MO-1068 (#504) is report only and
its report (evidence/MO-1068/cost-report.md) does not exist yet.
