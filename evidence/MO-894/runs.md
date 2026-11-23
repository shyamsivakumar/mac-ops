# MO-894 runs

Proof command: the ticket one-liner (board_io.HERDR_PROJECTS patched to a counting shim).

## On origin/main (red)
```
...
----------------------------------------------------------------------
Ran 3 tests in 0.014s

OK
Traceback (most recent call last):
  File "<string>", line 1, in <module>
AssertionError: board CLI called from a test
exit 1
```

## On the head (green)
```
...
----------------------------------------------------------------------
Ran 3 tests in 0.001s

OK
exit 0
```

## Fast-check isolation row (M1, remote run at d65bcead)

test isolation: no live gh call or log row | passed | no call the fake `gh` refused (no `pr view 169` refusal); 700 tests ran. Full row in check-proof.md.
