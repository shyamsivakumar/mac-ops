# MO-777 runs

The lane module imports `alarms` from `coordinator/overnight`, so both ticket-proof runs set `PYTHONPATH=coordinator/overnight`. All runs use temp state, journal and board dirs.

## Ticket proof command

Before (base `d00d49a0`, scratch worktree):

```
KeyError: 'promote_experiment'
```

After (branch head):

```
promoted undone
```

## Drill

Real functions; `compare_decision` is stubbed to a fixed string because a real winning journal needs 130+ tickets. The real compare call on an empty journal returns None.

```
journal: <tmp>/factory/state.json unreadable, no promotion applies: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
journal: <tmp>/factory/state.json is not an object, no promotion applies
== 1. no-experiment live case (real factory.json, experiments [])
registered: []
state.json exists: False | journal rows: [] | board: [] | ledger: {}
== 2. builder win: promote, card, 20 percent holdback
PROMOTION exp-b promoted, undo card raised
state: {'exp-b': {'state': 'promoted', 'promoted_at': 1795734094.199669, 'holdback_percent': 20}}
board: ['promoted-exp-b'] | journal: ['experiment_promoted', 'alarm_raised']
control share before promotion 0.497, after 0.205, stable across calls: True
control share at day 13: 0.205, at day 15: 0.000
second check same day (ledger throttle), board: ['promoted-exp-b']
== 3. one promotion matures at a time
PROMOTION exp-c refused, exp-b is still inside its 14 days
promote exp-c while exp-b is inside 14 days -> None | state keys: ['exp-b'] | journal: ['experiment_promoted', 'alarm_raised', 'experiment_promotion_refused']
promote exp-c at day 15 -> card
== 4. undo drill, timed end to end
PROMOTION exp-b promoted, undo card raised
promoted control share 0.205, after undo 1.000, card removed: True
state: {'exp-b': {'state': 'undone', 'promoted_at': 1795734094.45856, 'holdback_percent': 20, 'undone_at': 1795734094.505281}} | journal: ['experiment_promoted', 'alarm_raised', 'experiment_undone', 'alarm_withdrawn']
promote to undo took 0.05 s of lane time (limit 300 s)
CLI undo on an already undone experiment: exp-b is not promoted 
== 5. gate-side win raises a card only
PROMOTION exp-g is gate-side, board card raised
board: ['promote-click-exp-g'] | state.json exists: False | journal: ['experiment_needs_click', 'alarm_raised'] | arm share unchanged: True
== 6. malformed state.json
'{not json' -> control share 0.497 | file untouched: True | board: []
'[1, 2]' -> control share 0.497 | file untouched: True | board: []
'{"exp-b": {"state": "pro' -> control share 0.497 | file untouched: True | board: []
== 7. breach inside the window undoes
PROMOTION exp-b promoted, undo card raised
PROMOTION exp-b undone, control wins on the holdback
state: undone | board: [] | journal: ['experiment_promoted', 'alarm_raised', 'experiment_undone', 'alarm_withdrawn']
```

After an undo the experiment is over and every new cluster gets control (share 1.000, asserted in the drill); re-registering under a new name restarts it.
