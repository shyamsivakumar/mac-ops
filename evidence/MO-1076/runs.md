# Proof runs for #1076

## Red on origin/main

`scripts/walk_check.py` does not exist on origin/main, so the proof command `test -f scripts/walk_check.py` exits 1.

## passing run

```
$ python3 scripts/walk_check.py
walk PASS 3 steps (tick, gate, card); logs <tmp>
exit 0
```

## corrupt gate fixture (final line VERDICT: MAYBE)

```
$ python3 scripts/walk_check.py --gate-fixture <scratch>/gate-bad.json
walk FAIL step gate (result check failed); logs <tmp>
exit 1
```

## corrupt queue fixture (not JSON)

```
$ python3 scripts/walk_check.py --queue-fixture <scratch>/queue-bad.json
walk FAIL step tick (result check failed); logs <tmp>
exit 1
```

## missing gate fixture

```
$ python3 scripts/walk_check.py --gate-fixture <scratch>/missing.json
walk FAIL step gate (fixture unreadable: [Errno 2] No such file or directory: '<scratch>/missing.json'); logs <tmp>
exit 1
```

## step timeout 0.05s (hang)

```
$ python3 scripts/walk_check.py --step-timeout 0.05
walk FAIL step tick (hung past 0.05s); gate (hung past 0.05s); card (hung past 0.05s); logs <tmp>
exit 1
```
