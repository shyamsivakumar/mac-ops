# MO-777 runs

The lane module imports `alarms` from `coordinator/overnight`, so the ticket-proof runs set `PYTHONPATH=coordinator/overnight`. All runs use temp state, journal and board dirs.

## Ticket proof command

Before (base `d00d49a0`, scratch worktree):

```
KeyError: 'promote_experiment'
```

After (branch head):

```
promoted undone
```

## Drills

Real lane and scorecard functions. Sections 1 to 6 and 8 to 11 stub `compare_decision` (a real winning journal needs 130+ tickets) or fault it on purpose. The `drill777c` block runs the real `scorecard compare` through `compare_decision` on a synthetic journal with the promotion 22 days old, once where the holdback loses and once where it wins. The `window777` block runs the real CLI with `--since` and `--until`: the plain read of the first 10 tickets is the pre-promotion cohort ("no difference"), the windowed read sees only the 10 post-promotion tickets and says "control wins". After an undo every new cluster gets control (share 1.000, asserted in the undo drill).

```
### drill777
journal: <tmp>/factory/state.json unreadable, no promotion applies: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
journal: <tmp>/factory/state.json is not an object, no promotion applies
== 1. no-experiment live case (real factory.json, experiments [])
registered: []
state.json exists: False | journal rows: [] | board: [] | ledger: {}
== 2. builder win: promote, card, 20 percent holdback
PROMOTION exp-b promoted, undo card raised
state: {'exp-b': {'state': 'promoted', 'promoted_at': 1795739552.056062, 'holdback_percent': 20}}
board: ['promoted-exp-b'] | journal: ['alarm_raised', 'experiment_promoted']
control share before promotion 0.497, after 0.205, stable across calls: True
control share at day 13: 0.205, at day 15: 0.000
second check same day (ledger throttle), board: ['promoted-exp-b']
== 3. one promotion matures at a time
PROMOTION exp-c refused, exp-b is still inside its 14 days
promote exp-c while exp-b is inside 14 days -> False | state keys: ['exp-b'] | journal: ['alarm_raised', 'experiment_promoted', 'experiment_promotion_refused']
promote exp-c at day 15 -> card
== 4. undo drill, timed end to end
PROMOTION exp-b promoted, undo card raised
promoted control share 0.205, after undo 1.000, card removed: True
state: {'exp-b': {'state': 'undone', 'promoted_at': 1795739552.390574, 'holdback_percent': 20, 'undone_at': 1795739552.447791}} | journal: ['alarm_raised', 'experiment_promoted', 'experiment_undone', 'alarm_withdrawn']
promote to undo took 0.06 s of lane time (limit 300 s)
CLI undo on an already undone experiment: exp-b is not promoted 
== 5. gate-side win raises a card only
PROMOTION exp-g is gate-side, board card raised
board: ['promote-click-exp-g'] | state.json exists: True | journal: ['alarm_raised', 'experiment_needs_click'] | arm share unchanged: True
== 6. malformed state.json
'{not json' -> control share 0.497 | file untouched: True | board: []
'[1, 2]' -> control share 0.497 | file untouched: True | board: []
'{"exp-b": {"state": "pro' -> control share 0.497 | file untouched: True | board: []
### drill777b
== 8. compare raising, compare printing nothing
PROMOTION exp-b compare failed: boom
raising -> None
empty -> None
PROMOTION exp-b compare failed: boom
check_experiments survived, state.json exists: False
== 9. publish failing writes no promotion
PROMOTION exp-b not promoted, the undo card could not be raised
state.json exists: False | board: [] | control share 0.497
PROMOTION exp-b promoted, undo card raised
after publish works again, state: promoted | board: ['promoted-exp-b']
== 10. missing undo card is re-raised
board: ['promoted-exp-b']
== 11. gate click raised once over 3 simulated days
PROMOTION exp-g is gate-side, board card raised
day 1: board ['promote-click-exp-g'], needs_click rows 1
day 2: board ['promote-click-exp-g'], needs_click rows 1
day 3: board ['promote-click-exp-g'], needs_click rows 1
state: {'exp-g': {'state': 'click_raised', 'at': 1795739552.9505122}} | arm share unchanged: True
### drill777c
holdback loses (treatment passes in window): state promoted, breach_checked True, board ['promoted-exp-b']
  second tick runs no compare: ok
PROMOTION exp-b undone, control wins on the holdback
holdback wins (control passes in window): state undone, breach_checked True, board []
  second tick runs no compare: ok
### window777
plain compare (first 10 tickets are pre-promotion):
  -> no difference
windowed compare [promoted_at, promoted_at + 14 days], pre-promotion rows ignored:
  target 10 tickets, 10 assigned
  interim look skipped: the target was reached before its cohort settled
  final cohort is the first 10 tickets, read at 2026-10-08T16:13-07:00
  control: 5 tickets in 5 clusters, first-gate PASS 100.0%
  treatment: 5 tickets in 5 clusters, first-gate PASS 0.0%
  gap -100.0 points, cluster-bootstrap p 0.0005 (4000 draws, seed 7)
  time to merge: not enough merges
  control wins
```
