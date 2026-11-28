# MO-1387 (#1183) proof runs

## Red on origin/main

```
$ python3 -m unittest tests.test_models_block_provider.RiskyRoutingOrderTest
exit: 1

E
======================================================================
ERROR: RiskyRoutingOrderTest (unittest.loader._FailedTest)
----------------------------------------------------------------------
AttributeError: module 'tests.test_models_block_provider' has no attribute 'RiskyRoutingOrderTest'

----------------------------------------------------------------------
Ran 1 test in 0.000s

FAILED (errors=1)
```

## Green on branch

```
$ python3 -m unittest tests.test_models_block_provider.RiskyRoutingOrderTest
exit: 0

..................
----------------------------------------------------------------------
Ran 18 tests in 0.032s

OK
```
