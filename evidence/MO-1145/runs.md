# Proof runs for #1145

Proof command:

```
python3 -m unittest tests.test_coordq_capacity.CapacityTests.test_reviews_do_not_starve_builds tests.test_coordq_capacity.CapacityTests.test_builds_do_not_starve_reviews tests.test_coordq_capacity.CapacityTests.test_no_head_of_line_block
```

## Before: origin/main (the three tests do not exist there)

```
AttributeError: type object 'CapacityTests' has no attribute 'test_reviews_do_not_starve_builds'
AttributeError: type object 'CapacityTests' has no attribute 'test_builds_do_not_starve_reviews'
AttributeError: type object 'CapacityTests' has no attribute 'test_no_head_of_line_block'
Ran 3 tests in 0.000s
FAILED (errors=3)
```

## Before: origin/main coordq with this branch's test file

```
FAIL: test_reviews_do_not_starve_builds (tests.test_coordq_capacity.CapacityTests)
AssertionError: 6 != 3
FAIL: test_builds_do_not_starve_reviews (tests.test_coordq_capacity.CapacityTests)
AssertionError: Lists differ: ['ticket:o/r#1:a1'] != ['gate:o/r#1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa']
FAIL: test_no_head_of_line_block (tests.test_coordq_capacity.CapacityTests)
AssertionError: Lists differ: [] != ['ticket:o/r#2:a1']
FAIL: test_sends_hold_no_slot (tests.test_coordq_capacity.CapacityTests)
AssertionError: 0 != 30
Ran 4 tests in 0.060s
FAILED (failures=4)
```

## After: branch head

```
----------------------------------------------------------------------
Ran 3 tests in 0.054s

OK
```
