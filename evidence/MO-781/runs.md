# MO-781 runs

Proof command (narrowed by team lead: size is the only class routed; run with PYTHONPATH=coordinator/overnight because lane_driver imports alarms from its own folder):

```
PYTHONPATH=coordinator/overnight python3 -c 'import runpy; g=runpy.run_path("coordinator/overnight/lane_driver.py"); r=g["route_for"]; print(r("size"), r("logic"), r("environment"), r("minor_only"))'
```

## origin/main 04af24c1

```
KeyError: 'route_for'
```

## branch

```
recut today today today
```

Selftest case: the size block at the end of the gate-round-cap eval (journal class size, one files read per head, park once, partial, unreadable and small PRs keep the fix send).
