# MO-1388 (#1184) proof runs

## Red on origin/main

```
$ python3 -m unittest tests.test_reviewer_vendor_split.GateVerdictBuilderModelTest
exit: 1

E
======================================================================
ERROR: GateVerdictBuilderModelTest (unittest.loader._FailedTest)
----------------------------------------------------------------------
AttributeError: module 'tests.test_reviewer_vendor_split' has no attribute 'GateVerdictBuilderModelTest'

----------------------------------------------------------------------
Ran 1 test in 0.000s

FAILED (errors=1)
```

## Green on branch

```
$ python3 -m unittest tests.test_reviewer_vendor_split.GateVerdictBuilderModelTest
exit: 0

.....
----------------------------------------------------------------------
Ran 5 tests in 0.082s

OK
```
