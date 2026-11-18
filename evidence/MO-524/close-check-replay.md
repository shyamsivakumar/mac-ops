# Close checklist replay (MO-1077)

Three merged pull requests, run through the close checklist with
`python3 scripts/close_check_replay.py --pr 467 --pr 468 --pr 541` on 2026-11-18, with the
tickets that own them. The replay reads the merged tree from the local checkout, so it reads
no file contents through the GitHub API; the pull request and ticket metadata still
comes from `gh`.

close check: shyamsivakumar/mac-ops#467 (merge ad8b7543b3e5)
scope: pass - every changed file is inside the ticket's stated scope
proof file: fail - the pull request carries no proof file at evidence/MO-466/check-proof.md
checks: skipped - there is no proof file to read
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: FAIL shyamsivakumar/mac-ops#466
The work goes back to its builder and the ticket stays open.

close check: shyamsivakumar/mac-ops#468 (merge f489dfa94720)
scope: fail - outside the ticket's stated scope: coordinator/overnight/README.md
proof file: fail - the pull request carries no proof file at evidence/MO-466/check-proof.md
checks: skipped - there is no proof file to read
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: FAIL shyamsivakumar/mac-ops#466
The work goes back to its builder and the ticket stays open.

close check: shyamsivakumar/mac-ops#541 (merge ce79295f57ec)
scope: fail - the ticket names no file in this repository, so the scope cannot be judged: the ticket has to name the files it changes
proof file: fail - the proof file at evidence/check-proof.md is not part of this change: the pull request does not change it, so it is an earlier run's proof
checks: skipped - there is no proof file to read
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: FAIL shyamsivakumar/mac-ops#541
The work goes back to its builder and the ticket stays open.

## What each case shows

- #467 is inside its stated scope: the ticket declares
  `coordinator/bin/hourly_selftest.py` and every changed file is inside that scope. It
  carries no proof file at evidence/MO-466/check-proof.md, so the work goes back to its
  builder and the ticket stays open.
- #468 reaches outside that same declared scope: the diff touches
  coordinator/overnight/README.md, which the ticket's declaration does not name. The
  scope item fails and names the file, and the ticket stays open.
- #541 has a proof file that is an earlier run's proof: the file is on the base
  branch and the pull request does not change it. Its ticket declares its scope in prose,
  so the scope cannot be judged either. The work goes back to its builder and the
  ticket stays open.
- **The passing case.** No merged pull request in this repository passes the tightened rule,
  and the replay says so rather than dressing it up. A ticket is judged by its
  declaration, and the mac-ops template declares its scope in prose, so most tickets
  name no file and the scope cannot be judged: the close is refused. The pull
  requests that do declare files, #465 (MO-464), #467 and #468 (MO-466), #490 (MO-489),
  #492 (MO-491) and #529 (MO-496), all fail on the proof file or the scope. The
  passing path is proven by `tests/test_close_check.py`: a checklist with no blocking
  item closes the ticket and reports `RESULT: PASS`.

## The rules the checklist reads

- The ticket is the only authority for the scope. The pull request body is never read
  for it, so a pull request cannot widen the scope of the ticket that asked for the
  change.
- A ticket is judged by its declaration: the words after an "in" marker, and the
  section under a heading that declares the scope. The rest of the ticket is
  background, and a file named in the context section is a reference, not a
  permission. A ticket that declares no scope names no file, so its scope cannot be
  judged and the close is refused.
- A heading under a section belongs to that section, so it keeps the section's intent: a
  file under "### Protected files" inside "## Out of scope" stays excluded. Only a
  heading of the same level or higher ends the section.
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
