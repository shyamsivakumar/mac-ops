# Proof runs for #1168

Proof command:

```
python3 -m unittest tests.test_coordq_capacity.CapacityTests.test_lanes_max_fills_idle_slots tests.test_coordq_capacity.CapacityTests.test_no_repo_starves
```

## Before: the stacked base without lanesMax (this branch's tests)

```
ERROR: test_lanes_max_fills_idle_slots (tests.test_coordq_capacity.CapacityTests)
TypeError: __init__() takes 6 positional arguments but 7 were given
ERROR: test_no_repo_starves (tests.test_coordq_capacity.CapacityTests)
TypeError: lane_candidates() takes from 2 to 6 positional arguments but 7 were given
Ran 2 tests in 0.051s
FAILED (errors=2)
```

## After: branch head

```
----------------------------------------------------------------------
Ran 2 tests in 0.024s

OK
```
