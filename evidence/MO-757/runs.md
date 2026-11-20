# MO-757 runs

## Before (origin/main scorecard, same command)
```
KeyError: 'first_gate_pass'
```

## After (branch; second row set keys a PR-only gate row to its ticket and counts only the first verdict, so 0.0)
```
0.5
0.0
```

## ticket start emits one assigned (cmd_start run with stubbed gh/coordq, temp COORDQ_DIR, COORD_JOURNAL_DIR, HOME)
Two calls: first with no prior intent (attempt 1), second with one prior intent (attempt 2). Journal rows:
```
assigned        repo r/x ticket 5 attempt 1 data {"arm": null}
ticket_started  repo r/x ticket 5 attempt 1
ticket_started  repo r/x ticket 5 attempt 1   (second call; no second assigned)
```
Note: the proof command in the issue was adapted only by running the "before" against a copy of origin/main's scorecard (KeyError above). Real gate_verdict rows carry no ticket, so first_gate_pass maps their PR to a ticket through any row that has both.

## Cross-midnight (review fix: group by assignment day, look up the first verdict in the full journal)
Tickets 1 (assigned D 23:50, PASS at D+1 00:10) and 2 (assigned D 00:01, no verdict):
```
first_gate_pass(rows)                      -> 0.5
first_gate_pass(rows, D start, D end)      -> 0.5   (ticket 1 counts as passed for day D)
first_gate_pass(rows, D+1 start, D+1 end)  -> None  (no assignments that day)
original proof command                     -> 0.5
```
