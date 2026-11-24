# MO-918 runs

## Proof on origin/main (red)
```
Traceback (most recent call last):
  File "<string>", line 1, in <module>
AssertionError: [None, None, None]
```

## Extended case on origin/main code (red)
```
    exact(reconcile(), len(settled))
  File "/private/tmp/claude-501/-Users-shyamsivakumar-Code/c283b00e-e8c8-422f-9aa1-eb7c969bb5ce/scratchpad/main918/coordinator/overnight/selftest.py", line 87, in exact
    raise AssertionError(f"expected {expected!r}, got {actual!r}")
AssertionError: expected 9, got 6
```

## Proof on the branch (green)
```
```

## Extended case on the branch (green)
```
case ok
```
