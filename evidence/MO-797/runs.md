# MO-797 proof

Adapted from the ticket stub: the proof drives `_board_control_tick` with fake board and a 6-active, limit-0 fixture; a fresh sample raises the limit to the floor (7), a stale one holds at 0.

## main (26f8c6a8)
```
age 8s load_per_core 3.0 -> reason=await_healthy_window board_limit=0
age 8s load_per_core 1.0 -> reason=stale-telemetry board_limit=0
```

## head
```
age 8s load_per_core 3.0 -> reason=board_baseline_floor board_limit=7
age 8s load_per_core 1.0 -> reason=stale-telemetry board_limit=0
```
