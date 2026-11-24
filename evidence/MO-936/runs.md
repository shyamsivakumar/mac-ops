# MO-1252 runs

## Proof command on origin/main code (4dc5a538)
```
  File "<string>", line 1, in <module>
ModuleNotFoundError: No module named 'inbox_poll'
exit 1
```

## inbox eval (branch selftest.py) against flat origin/main code
```
    import inbox_poll as poll
ModuleNotFoundError: No module named 'inbox_poll'
exit 1
```

## Proof command on the branch (code commit 1722ddc2d3ec4a75f116ee0403f135f014f76b88)
```
exit 0
```

## inbox eval on the branch, in place
```
o/r: skipped a malformed pull request
inbox eval ok
exit 0
```

## inbox eval on the branch, flat copy of coordinator/bin and coordinator/overnight
```
o/r: skipped a malformed pull request
inbox eval ok
exit 0
```
