# Close checklist replay (MO-1077)

Three recent merged pull requests, run through the close checklist with
`python3 scripts/close_check_replay.py --pr 528 --pr 429 --pr 519` on 2026-11-18, with the
tickets that own them.

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

- #528 (the MO-521 ticket) passes every item. Its ticket names
  `coordinator/bin/gate_reviewers.py` and says its existing tests may change only as far
  as this needs. Both changed test files pin the model the change sets, so the
  clause reaches them and nothing else; the proof file is there and all nine of its
  checks passed.
- #429 (the MO-428 ticket) carries no proof file, so the work goes back to its
  builder and the ticket stays open. Its scope is inside the stated scope.
- #519 (the MO-517 ticket) touches `coordinator/bin/hourly_selftest.py` and
  `coordinator/overnight/selftest.py`, which its ticket never names, so the diff is
  outside the stated scope. The work goes back to its builder and the ticket stays
  open.

The scope comes from the ticket alone: the pull request body is not read for it, so
a pull request cannot widen the scope of the ticket that asked for the change.

A name the ticket excludes is not a permission. The words after an "out" marker, and
the words of a sentence that forbids a change, name what the ticket excludes, so a
change to one of them fails the scope item.

A ticket clause about its existing tests keeps its restriction. The clause lets a
test change when the test pins what the change pins, that is when the test and a
changed source file share a distinctive value, or when the test is the test of a
changed source file by name. A shared prefix is not a relationship:
`tests/test_close_window.py` is not the test of `close_check.py`.

A test ties to a source file only. Evidence is not a source, so a pull request
cannot add an evidence file that carries the name of its own test, and it cannot
copy a value from an unrelated test into a changed evidence file to tie that test.
A source file the ticket never names fails the scope item on its own, so tying to
one grants nothing.

The cost note item is skipped in all three: MO-1068 (#504) is report only and its
report (evidence/MO-1068/cost-report.md) does not exist yet.
