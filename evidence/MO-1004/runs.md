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
