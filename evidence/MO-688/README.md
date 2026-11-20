# MO-688: the factory event journal, and why its first close check failed

#690 (`272113c7`) added the factory event journal. `coordinator/bin/journal.py`
appends one JSON line per lifecycle event to
`~/Library/Logs/coordinator/events-YYYY-MM.jsonl`, and coordq, the lane,
ticket and the alarms writer each emit their events through it.

## What the close checklist said

The lane ran the close checklist on #690 against ticket #688 and it failed
on two items:

```
scope: fail - outside the ticket's stated scope: coordinator/bin/coordq, coordinator/bin/ticket, coordinator/overnight/alarms.py, coordinator/overnight/lane_driver.py, coordinator/overnight/selftest.py, scripts/mac_ops_fast_check.py
proof file: pass - evidence/MO-688/check-proof.md is present
checks: fail - the proof file lists a check that is not passed: $ COORD_JOURNAL_DIR=$T ticket show shyamsivakumar/mac-ops#688 (no result recorded), { (no result recorded), "repo": "shyamsivakumar/mac-ops", (no result recorded), ...
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: FAIL shyamsivakumar/mac-ops#688
```

## Why

Scope. The ticket named the emit points by function (`coordq` `cmd_start`,
`lane_driver` `act_on_pr`) and not by file path, and it did not name two
files the change needed. `coordinator/overnight/selftest.py` and
`scripts/mac_ops_fast_check.py` now point the journal at a scratch
directory, because the first check run wrote test events into the live
journal and the hourly selftest would have done it every hour. The scope
section was incomplete, not the change.

Checks. The checklist reads every line of the proof file that holds a pipe
as a table row, and every `name: passed` line as a result. The proof
carried the shell output of the acceptance runs (a `| head` command, a JSON
dump), so those lines were read as checks with no result.

## What this change does

- Corrects the ticket's scope section to name every file #690 changed, by
  path, with a one-line reason. The ticket is the only authority for the
  scope, so the correction is made there.
- Moves the run output out of `check-proof.md` into `runs.md`. The proof
  file keeps its check table and its checked commit (`05d3b0af`), and
  nothing else.
- Adds this README.

No code changes for this ticket.

## The close checklist after the correction

Read against #690 and the corrected ticket, with the proof read from this
checkout (the replay in `scripts/close_check_replay.py` reads a file at the
merge commit, and the merge commit of #690 still holds the old proof):

```
scope: pass - every changed file is inside the ticket's stated scope
proof file: pass - evidence/MO-688/check-proof.md is present
checks: pass - every one of the 14 checks the proof file lists passed
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: PASS shyamsivakumar/mac-ops#688
```

## Left for later

Nothing for the journal. A close of #688 that reads the proof at the merge
commit of #690 still sees the old proof, so the close has to run against a
pull request that changes `evidence/MO-688/check-proof.md`.
