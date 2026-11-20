# MO-533 runs

## Fake gh, swap_stage (python3 proof.py coordinator/bin/ticket)
```
stage swap stage:todo -> stage:started failed (offline): boom; o/r#7 has stage:todo and not stage:started
stage swap stage:todo -> stage:started failed (offline): boom; restoring stage:todo also failed (offline): boom; o/r#7 may have no stage label, check it by hand
== success
before: ['stage:todo', 'type:standard']
gh edit calls: [['o/r', '--add-label', 'stage:started', '--remove-label', 'stage:todo']]
after:  ['stage:started', 'type:standard']
== edit fails, restore works
before: ['stage:todo', 'type:standard']
exit 1
gh edit calls: [['o/r', '--add-label', 'stage:started', '--remove-label', 'stage:todo'], ['o/r', '--add-label', 'stage:todo', '--remove-label', 'stage:started']]
after:  ['stage:todo', 'type:standard']
== edit and restore fail
before: ['stage:todo', 'type:standard']
exit 1
gh edit calls: [['o/r', '--add-label', 'stage:started', '--remove-label', 'stage:todo'], ['o/r', '--add-label', 'stage:todo', '--remove-label', 'stage:started']]
after:  ['stage:todo', 'type:standard']
```

## Existing checks
- python3 coordinator/overnight/selftest.py: OK (start-routing runs cmd_start with gh patched)
- scripts/mac_ops_fast_check.py --proof evidence/MO-533/check-proof.md: passed, 85 tests

Delivery: ticket has no delivery label step on main (grep for stage:delivered, stage:review finds none), so only start changed.
