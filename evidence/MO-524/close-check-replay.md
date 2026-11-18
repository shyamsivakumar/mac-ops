# Close checklist replay (MO-1077)

Three merged pull requests, run through the close checklist with
`python3 scripts/close_check_replay.py --pr 540 --pr 541 --pr 492` on 2026-11-18, with the
tickets that own them. The replay reads the merged tree from the local checkout, so it reads
no file contents through the GitHub API; the pull request and ticket metadata still
comes from `gh`.

close check: shyamsivakumar/mac-ops#540 (merge cbb186979c84)
scope: fail - outside the ticket's stated scope: coordinator/mods/cockpit/flowlog.js, coordinator/mods/cockpit/main.js, evidence/check-proof.md
proof file: pass - evidence/check-proof.md is present
checks: pass - every one of the 4 checks the proof file lists passed
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: FAIL shyamsivakumar/mac-ops#540
The work goes back to its builder and the ticket stays open.

close check: shyamsivakumar/mac-ops#541 (merge ce79295f57ec)
scope: fail - outside the ticket's stated scope: coordinator/mods/cockpit/asks.js, coordinator/mods/cockpit/hub.js, coordinator/mods/cockpit/main.js, coordinator/mods/cockpit/ui.js
proof file: fail - the proof file at evidence/check-proof.md is not part of this change: the pull request does not change it, so it is an earlier run's proof
checks: skipped - there is no proof file to read
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: FAIL shyamsivakumar/mac-ops#541
The work goes back to its builder and the ticket stays open.

close check: shyamsivakumar/mac-ops#492 (merge 13c79aedc6fa)
scope: fail - the ticket names no file in this repository, so the scope cannot be judged: the ticket has to name the files it changes
proof file: fail - the pull request carries no proof file at evidence/MO-491/check-proof.md
checks: skipped - there is no proof file to read
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: FAIL shyamsivakumar/mac-ops#491
The work goes back to its builder and the ticket stays open.

## What each case shows

- #540 is outside its stated scope: the diff reaches coordinator/mods/cockpit/flowlog.js,
  coordinator/mods/cockpit/main.js and evidence/check-proof.md, which the ticket never
  names. Its proof file is present and all four of its checks passed, so the scope is
  what stops it. The work goes back to its builder and the ticket stays open.
- #541 is outside its stated scope as well, and its proof file is an earlier run's proof:
  the file is on the base branch and the pull request does not change it. The work
  goes back to its builder and the ticket stays open.
- #492 carries no proof file at all at evidence/MO-491/check-proof.md, so the work goes
  back to its builder and the ticket stays open.
- **The passing case.** No merged pull request in this repository passes the tightened rule,
  and the replay says so rather than dressing it up. A ticket that declares its
  scope is judged by that declaration, and the mac-ops template declares its scope in
  prose, so the ticket names no file and the scope cannot be judged: the close is
  refused. The only pull requests that carry a proof file are #498 and #529 (MO-496),
  #510 (MO-501), #519 (MO-517), #528 (MO-521), #534 (MO-530), #535 (MO-533), #536
  (MO-532), #537 (MO-531), #540, #541 and #499 (MO-497), and every one of them fails
  the scope item. The passing path is proven by `tests/test_close_check.py`: a
  checklist with no blocking item closes the ticket and reports `RESULT: PASS`.

## The rules the checklist reads

- The ticket is the only authority for the scope. The pull request body is never read
  for it, so a pull request cannot widen the scope of the ticket that asked for the
  change.
- A ticket that declares its scope is judged by that declaration. The rest of the ticket
  is background: a file named in the context section is a reference, not a
  permission.
- A declared directory bounds the scope: every changed path under it is inside the
  boundary, and every changed path outside it is not.
- An exclusion is not a permission. The words after an "out" marker, the list
  entries under it and the rest of its section are exclusions, so a change to one of
  them fails the scope item, and an excluded name never widens the scope.
- A test changes when the ticket names that test, or when it is the test of a file the
  change touches by name. No string ties a test to a change: a pull request can
  write the same string into an unrelated test and into a file it changed, whether
  the change introduced that string or not, so a shared string proves nothing.
  Evidence is not a source, so a pull request cannot supply the file that
  authorizes its own test change.
- The proof file has to be part of the change. A proof file that is already on the
  base branch is an earlier run's proof, so the path has to be among the files the
  pull request changes.
- A cost note carries a value. "Cost:" on its own is a label without a note, so it
  waives nothing.

The cost note item is skipped in all three: MO-1068 (#504) is report only and its report
(evidence/MO-1068/cost-report.md) does not exist yet.
