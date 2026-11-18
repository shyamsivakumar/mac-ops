# Close checklist replay (MO-1077)

Three merged pull requests, run through the close checklist with
`python3 scripts/close_check_replay.py --pr 528 --pr 492 --pr 519` on 2026-11-18, with the
tickets that own them. The replay reads the merged tree from the local checkout,
so it runs without the GitHub API.

close check: shyamsivakumar/mac-ops#492 (merge 13c79aedc6fa)
scope: pass - every changed file is inside the ticket's stated scope
proof file: fail - the pull request carries no proof file at evidence/MO-491/check-proof.md
checks: skipped - there is no proof file to read
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: FAIL shyamsivakumar/mac-ops#491
The work goes back to its builder and the ticket stays open.

close check: shyamsivakumar/mac-ops#519 (merge 431d81f647b8)
scope: fail - outside the ticket's stated scope: coordinator/bin/hourly_selftest.py, coordinator/overnight/selftest.py
proof file: pass - evidence/MO-517/check-proof.md is present
checks: pass - every one of the 7 checks the proof file lists passed
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: FAIL shyamsivakumar/mac-ops#517
The work goes back to its builder and the ticket stays open.

close check: shyamsivakumar/mac-ops#429 (merge 580535a0b096)
scope: pass - every changed file is inside the ticket's stated scope
proof file: fail - the pull request carries no proof file at evidence/MO-428/check-proof.md
checks: skipped - there is no proof file to read
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: FAIL shyamsivakumar/mac-ops#428
The work goes back to its builder and the ticket stays open.

close check: shyamsivakumar/mac-ops#528 (merge 62676880acac)
scope: pass - every changed file is inside the ticket's stated scope
proof file: pass - evidence/MO-521/check-proof.md is present
checks: pass - every one of the 9 checks the proof file lists passed
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: PASS shyamsivakumar/mac-ops#521

## What each case shows

- #528 (the MO-521 ticket) passes every item. Its ticket names
  `coordinator/bin/gate_reviewers.py` and says its existing tests may change only as far
  as this needs. Both changed test files pin the model the change sets, so the
  clause reaches them and nothing else; the proof file is there and all nine of its
  checks passed.
- #492 (the MO-491 ticket) is inside its stated scope, but the pull request carries
  no proof file at evidence/MO-491/check-proof.md, so the work goes back to its
  builder and the ticket stays open.
- #519 (the MO-517 ticket) carries a proof file whose seven checks all passed, but
  the diff touches coordinator/bin/hourly_selftest.py and
  coordinator/overnight/selftest.py, which its ticket never names, so the diff is
  outside the stated scope: the work goes back to its builder and the ticket
  stays open.

## The rules the checklist reads

- The ticket is the only authority for the scope. The pull request body is never read
  for it, so a pull request cannot widen the scope of the ticket that asked for the
  change.
- An exclusion is not a permission. The words after an "out" marker, the list
  entries under it and the rest of its section are exclusions, so a change to one of
  them fails the scope item, and an excluded name never widens the scope.
- A test ties to a source file by its name, and to a value only when the change set
  that value: a pull request that copies a string from an unrelated test into a
  file it changed ties nothing, because the change never introduced the string.
  Evidence is not a source, so a pull request cannot supply the file that
  authorizes its own test change.

The cost note item is skipped in all three: MO-1068 (#504) is report only and its
report (evidence/MO-1068/cost-report.md) does not exist yet.
