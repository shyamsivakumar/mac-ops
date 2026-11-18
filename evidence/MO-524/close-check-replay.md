# Close checklist replay (MO-1077)

Three recent merged pull requests, run through the close checklist with
`python3 scripts/close_check_replay.py --pr 528 --pr 513 --pr 529` on 2026-11-18.

close check: shyamsivakumar/mac-ops#528 (merge 62676880acac)
scope: pass - every changed file is inside the ticket's stated scope
proof file: pass - evidence/MO-521/check-proof.md is present
checks: pass - every one of the 9 checks the proof file lists passed
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: PASS shyamsivakumar/mac-ops#521

close check: shyamsivakumar/mac-ops#513 (merge d81fe36e2d77)
scope: fail - outside the ticket's stated scope: coordinator/config/agents/code-reviewer.md
proof file: fail - the pull request carries no proof file at evidence/MO-503/check-proof.md
checks: skipped - there is no proof file to read
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: FAIL shyamsivakumar/mac-ops#503
The work goes back to its builder and the ticket stays open.

close check: shyamsivakumar/mac-ops#529 (merge def2918d6cb8)
scope: fail - outside the ticket's stated scope: coordinator/overnight/lane_driver.py, coordinator/overnight/selftest.py
proof file: pass - evidence/MO-496/check-proof.md is present
checks: pass - every one of the 6 checks the proof file lists passed
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: FAIL shyamsivakumar/mac-ops#496
The work goes back to its builder and the ticket stays open.

## What each case shows

- #528 (Refs #521) passes every item: the diff stays inside the ticket's scope,
  the proof file is there and every check in it passed.
- #513 (Refs #503) has no proof file, so the work goes back to its builder and the
  ticket stays open. Its scope item also fails: the ticket never names
  coordinator/config/agents/code-reviewer.md.
- #529 (Refs #496) touches coordinator/overnight/lane_driver.py and
  coordinator/overnight/selftest.py, which its ticket never names, so the diff is
  outside the stated scope. The work goes back to its builder and the ticket stays
  open.

The cost note item is skipped in all three: MO-1068 (#504) is report only and
its report (evidence/MO-1068/cost-report.md) does not exist yet.
