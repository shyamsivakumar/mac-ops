# MO-533 runs

## Fake gh, swap_stage success and failure
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

## Fake gh, label creation (a missing label makes the edit fail)
calls shows the gh subcommands in order; the label call is gh label create stage:started --force.
```
== repo without the label
repo has stage:started: False
issue before: ['stage:todo', 'type:standard']
calls: ['label create stage:started -R', 'issue edit 7'] 
issue after: ['stage:started', 'type:standard']
== repo with the label
repo has stage:started: True
issue before: ['stage:todo', 'type:standard']
calls: ['label create stage:started -R', 'issue edit 7'] 
issue after: ['stage:started', 'type:standard']
== second start in same process, same repo
repo has stage:started: False
issue before: ['stage:todo', 'type:standard']
calls: ['label create stage:started -R', 'issue edit 7', 'issue edit 7'] 
issue after: ['stage:started', 'type:standard']
```

## Existing checks
- python3 coordinator/overnight/selftest.py: OK (start-routing runs cmd_start with gh patched)
- scripts/mac_ops_fast_check.py --proof evidence/MO-533/check-proof.md: passed

Delivery: ticket has no delivery label step on main (stage:delivered and stage:review appear nowhere), so only start changed.
ticket labels --apply also creates stage:started now.
