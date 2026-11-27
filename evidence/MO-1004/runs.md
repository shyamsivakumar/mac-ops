# MO-1004 proof runs

Proof command: `python3 coordinator/overnight/selftest.py | grep -c "PASS stale-started-refill"` (the selftest prints `PASS <case>`, so the ticket grep text `case stale-started-refill` is adapted to that format).

## Red on origin/main (no case registered; the extracted-tree selftest hung and was stopped, so the name count came from the killed run)
```
0
```
## Red: new case against origin/main lane_driver
```
FAIL stale-started-refill: expected 'DRY release [7]', got 'nothing ready'
```
## Green on head
```
1
```
FAIL lines on head:
```
0
```

## Rework: journal age rule (30 min)
```
1
```
A 5-minute-old or unreadable ticket_started row is left alone; a 2-hour-old row is released (selftest case stale-started-refill).

## Gate fix: retained journal months

The stale-started-refill selftest uses real temporary receipts and journal files, with the clock fixed at 2025-03-01 00:30 UTC. The lookup is no longer mocked. A two-hour-old start lives in February and a 90-day-old start lives in December. Both release the orphan; recent and missing starts remain untouched, and live builders/open PRs remain protected.

The same selftest was run against the original lookup loaded from gate head 169fabd591d1caec3fa31bae222e8d0959d00aec in memory, then against the fixed lookup:

```
RED original lookup: expected 'DRY release [7]', got 'nothing ready'
GREEN retained-month lookup: PASS stale-started-refill; real February and December journals on 2025-03-01
```

The fix scans all retained `events-YYYY-MM.jsonl` files in the existing journal directory. It does not depend on month length and does not discard older starts through an arbitrary time window. Cost grows with retained journal history; journal retention is unchanged.

Device, handset and live-service testing was waived, not failed; no live cases were run. The unrelated root evidence/check-proof.md is left untouched; the ticket proof is evidence/MO-1004/check-proof.md.
