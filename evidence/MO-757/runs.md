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
