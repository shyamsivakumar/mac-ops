# Close checklist replay (MO-1077)

Two merged pull requests, run through the close checklist with
`python3 scripts/close_check_replay.py --pr 492 --pr 519` on 2026-11-18, with the tickets
that own them. The replay reads the merged tree from the local checkout, so it reads
no file contents through the GitHub API; the pull request and ticket metadata still
comes from `gh`.

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

## What each case shows

- #492 (the MO-491 ticket) is inside its stated scope, but the pull request carries
  no proof file at evidence/MO-491/check-proof.md, so the work goes back to its
  builder and the ticket stays open.
- #519 (the MO-517 ticket) carries a proof file whose seven checks all passed, but
  the diff touches coordinator/bin/hourly_selftest.py and
  coordinator/overnight/selftest.py, which its ticket never names, so the diff is
  outside the stated scope: the work goes back to its builder and the ticket
  stays open.
- **The passing case.** No merged pull request in this repository passes the
  tightened rule, and the replay says so rather than dressing it up. The checklist
  was read over every merged pull request here and over every open one: the only
  pull requests that carry a proof file are #498 and #529 (MO-496), #510 (MO-501),
  #519 (MO-517), #528 (MO-521), #534 (MO-530), #535 (MO-533), #536 (MO-532), #537
  (MO-531) and #499 (MO-497), and each of their tickets names at most one file, so
  each of them fails the scope item. Every mac-ops ticket describes its area in
  prose, so the ticket authorizes no file, so the scope cannot be judged and the
  close is refused. The passing path is proven by `tests/test_close_check.py`: a
  checklist with no blocking item closes the ticket and reports `RESULT: PASS`.

## The rules the checklist reads

- The ticket is the only authority for the scope. The pull request body is never read
  for it, so a pull request cannot widen the scope of the ticket that asked for the
  change.
- An exclusion is not a permission. The words after an "out" marker, the list
  entries under it and the rest of its section are exclusions, so a change to one of
  them fails the scope item, and an excluded name never widens the scope.
- A test changes when the ticket names that test, or when it is the test of a file the
  change touches by name. No string ties a test to a change: a pull request can
  write the same string into an unrelated test and into a file it changed, whether
  the change introduced that string or not, so a shared string proves nothing.
  Evidence is not a source, so a pull request cannot supply the file that
  authorizes its own test change.
- The ticket's own evidence travels with the change: a file under the ticket's own
  evidence directory is in scope, and another ticket's evidence is not. A pull
  request scoped to one file cannot rewrite another ticket's proof file and still
  pass the scope item.
- A proof row that carries no result blocks the close. An incomplete row is never
  dropped: a row that names a check and a command but omits its result fails the
  item, so a passing check that was never written cannot read as passed. The
  table's header is recognized once, as the whole header row, so a later row whose
  first cell reads "check" is a check like any other and a recorded failure cannot
  hide behind it. The separator is recognized as the whole row too: a row whose
  first cell only marks it as a separator is a check with a malformed name, and a
  malformed row blocks the close. A result written outside the table is a check
  too, so "heavy help: failed" in the proof file blocks the close as well. The
  header is the whole header row, so a first row that is not one is a check, and a
  command that holds a pipe is one cell, so a row is split on the pipes that are
  not escaped. A Markdown row does not have to carry its outer pipes, and a line
  inside the table that is not a row is a malformed row, so nothing the table
  holds is dropped.

The cost note item is skipped in both: MO-1068 (#504) is report only and its report
(evidence/MO-1068/cost-report.md) does not exist yet.
