# MO-1385 (#1181) proof runs

## Red on origin/main

```
$ python3 -m unittest tests.test_overnight_board.T3ProjectListPaginationTest
exit: 1

E
======================================================================
ERROR: T3ProjectListPaginationTest (unittest.loader._FailedTest)
----------------------------------------------------------------------
AttributeError: module 'tests.test_overnight_board' has no attribute 'T3ProjectListPaginationTest'

----------------------------------------------------------------------
Ran 1 test in 0.000s

FAILED (errors=1)
```

## Green on branch

```
$ python3 -m unittest tests.test_overnight_board.T3ProjectListPaginationTest
exit: 0

..
----------------------------------------------------------------------
Ran 2 tests in 0.076s

OK
```

## Regression check (`evidence/MO-1103/proof_dryrun.py`)

```
$ python3 -I evidence/MO-1103/proof_dryrun.py
exit: 0

dry run: 7 completed unsettled threads
  settle:    1 pull request merged or closed
  settle:    1 ticket issue closed
  settle:    1 gate verdict recorded
  skip:      1 pinned
  skip:      1 Ascend or slash-eureka
  skip:      2 work not finished
  sample: merged 't' (pull request merged or closed)
  sample: losed-ticket 't' (ticket issue closed)
  sample: verdict 't' (gate verdict recorded)

PASS
```
