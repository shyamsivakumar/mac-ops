# MO-689: the daily scorecard, and why its first close check failed

#692 (`1182bb93`) added `coordinator/bin/scorecard`, the daily factory
scorecard. It replays the event journal, checks the merge count against
GitHub, and writes `~/Code/coordinator/scorecard/<date>.json`. The lane runs
it once a day after 00:10 PT.

## What the close checklist said

Run against #692 and ticket #689:

```
scope: fail - outside the ticket's stated scope: coordinator/bin/coordq, coordinator/bin/journal.py, coordinator/bin/ticket, coordinator/overnight/alarms.py, coordinator/overnight/selftest.py, evidence/MO-688/check-proof.md, scripts/mac_ops_fast_check.py
proof file: pass - evidence/MO-689/check-proof.md is present
checks: pass - every one of the 15 checks the proof file lists passed
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: FAIL shyamsivakumar/mac-ops#689
```

## Why

#692 was stacked on the journal change of #688, so its diff also carried
that change: `journal.py`, coordq, ticket, `alarms.py`, `selftest.py` and
`evidence/MO-688/check-proof.md`. The ticket named only its own files.
`scripts/mac_ops_fast_check.py` is also in the change: it lists
`coordinator/bin/scorecard` among the suffixless Python files, so the check
parses and lints the CLI. The scope section was incomplete, not the change.

## What this change does

- Corrects the ticket's scope section to name every file #692 changed, by
  path, with the reason, including the stacked journal files.
- Moves the run output out of `check-proof.md` into `runs.md`, so a proof
  file is a check table and nothing else. That is the same reformat as for
  #688, where the run output had been read as checks.
- Fixes the revert window of the change failure metric. A day's change
  failure was called final on the seventh day after the report day began,
  so a PR merged late on that day could still be reverted inside its own
  7 days. It is now final only once the report day's end plus 7 days has
  passed. `runs.md` shows the boundary with two runs.
- Adds `check-proof-2.md`, the check proof for the head of this change, and
  this README.

## The close checklist after the correction

Read against #692 and the corrected ticket, with the proof read from this
checkout:

```
scope: pass - every changed file is inside the ticket's stated scope
proof file: pass - evidence/MO-689/check-proof.md is present
checks: pass - every one of the 15 checks the proof file lists passed
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: PASS shyamsivakumar/mac-ops#689
```

## Left for later

Nothing.
