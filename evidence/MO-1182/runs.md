# MO-1386 (#1182) proof runs

## Red on origin/main

```
$ python3 -m unittest tests.test_coordinator_mirror.CoordPiLauncherTest
exit: 1

E
======================================================================
ERROR: CoordPiLauncherTest (unittest.loader._FailedTest)
----------------------------------------------------------------------
AttributeError: module 'tests.test_coordinator_mirror' has no attribute 'CoordPiLauncherTest'

----------------------------------------------------------------------
Ran 1 test in 0.000s

FAILED (errors=1)
```

## Green on branch

```
$ python3 -m unittest tests.test_coordinator_mirror.CoordPiLauncherTest
exit: 0

.
----------------------------------------------------------------------
Ran 1 test in 0.010s

OK
```
