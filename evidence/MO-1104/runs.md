# MO-1104 proof

## Ticket proof command
```
on origin/main:
False
exit 1
on the branch:
True
exit 0
```

## Selftest cases dead_run_no_receipt and dead_run_recovery, new fixtures, no live calls
```
origin/main lane_driver.py with the branch selftest.py:
  File "/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/unittest/mock.py", line 1378, in get_original
    raise AttributeError(
AttributeError: <module 'lane_driver' from '/private/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmp.jkTtXRmXyX/coordinator/overnight/./lane_driver.py'> does not have the attribute 'dead_pr_head'
branch:
dead_run_no_receipt and dead_run_recovery: pass
```
