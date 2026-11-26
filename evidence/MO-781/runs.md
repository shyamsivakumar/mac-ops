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

## Size phrase test on the 135 hand-labelled FAIL reports

A FAIL is parked only when the lead paragraph of the report matches `SIZE_BLOCKER` (150 lines, a stop at 150, size cap or line cap), the PR is over the cap by `code_size`, and neither `type:large` nor `gate:whole` applies. Matches against the hand labels (causes-a.jsonl, causes-b.jsonl):

- primary size_cap: 6 reports, 6 match ([1873, 2019, 2206, 2270, 2512, 2572])
- over cap, primary other: 10 reports, 0 match
- not over cap: 119 reports, 0 match

A miss keeps today's fix send. The 6 primary size_cap reports all match; no report of another cause matches.
