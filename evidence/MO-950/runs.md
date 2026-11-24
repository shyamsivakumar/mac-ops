# MO-950 runs

## Ticket proof on origin/main
```
AttributeError: module 'cq' has no attribute 'round_caps'
exit 1
```

## Ticket proof on the branch
```
round caps: roundcap:o/r#3 is not a round cap entry, skipped
exit 0
```

## gate-round-cap eval (extended selftest.py) on origin/main code
```
AttributeError: <module 'lane_driver' from '/Users/shyamsivakumar/Code/mac-ops-worktrees/mo950-main/coordinator/overnight/lane_driver.py'> does not have the attribute 'round_cap_to_board'
exit 1
```

## gate-round-cap and decisions-board-guard on the branch
```
PASS gate-round-cap
PASS decisions-board-guard
exit 0
```
