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
scope: skipped - the ticket names no file in this repository, so the scope cannot be judged
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

## The change checked against itself

The checklist run on this pull request, before it merged:

    $ python3 coordinator/bin/close_check.py --repo shyamsivakumar/mac-ops --pr 538 --issue 524
    close check: shyamsivakumar/mac-ops#538 (merge 4df693050bfa)
    scope: skipped - the ticket names no file in this repository, so the scope cannot be judged
    proof file: pass - evidence/MO-524/check-proof.md is present
    checks: pass - every one of the 10 checks the proof file lists passed
    cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
    RESULT: PASS shyamsivakumar/mac-ops#524

This is the case the checklist has to get right at its own close: the ticket
names its area in prose (`In: checklist at close`), so there is no file to
judge the scope against and the item skips instead of failing every file.

## What each case shows

- #528 (MO-521) passes every item: the diff stays inside the ticket's scope,
  the proof file is there and every check in it passed.
- #513 (MO-503) has no proof file, so the work goes back to its builder and the
  ticket stays open. Its scope item skips: the ticket names its area by a home
  path (`~/Code/coordinator/inbox/...`) and a directory, never a file in this
  repository, so there is no file for the item to judge.
- #529 (MO-496) touches coordinator/overnight/lane_driver.py and
  coordinator/overnight/selftest.py, which its ticket never names, so the diff is
  outside the stated scope: the ticket names `decisions.json`, a file of this
  repository, so the item judges the diff and fails it. The work goes back to its
  builder and the ticket stays open.

The cost note item is skipped in all three: MO-1068 (#504) is report only and
its report (evidence/MO-1068/cost-report.md) does not exist yet.
