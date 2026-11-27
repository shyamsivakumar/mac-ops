# MO-1331 proof runs (issue 1079)

## origin/main 906862ac (red)
```
              ...
coordq: error: argument cmd: invalid choice: 'kill' (choose from 'start', 'create', 'list', 'drop', 'status', 'spend', 'decision', 'actrate', 'wait', 'waits', 'dispatch', 'gatekeep', 'gate', 'fix')
exit 2
```

## head (green)
```
kill switch: on, no new work starts
kill switch is on: no new work starts, running work is left alone
exit 0
kill switch: off
{"trial": "t", "killSwitch": "off", "capUsd": 25, "days": 7, "runs": 1, "tokens": 100, "usd": 26, "runsWithoutCost": 0, "dayOfTrial": 10, "overCap": true}
{"trial": "none", "killSwitch": "off", "capUsd": "unknown", "days": "unknown", "runs": 0, "tokens": "unknown", "usd": "unknown", "runsWithoutCost": 0}
```
