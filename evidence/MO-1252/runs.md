# MO-1252 runs

## Proof command on origin/main (adc3269b)
```
  File "<string>", line 1, in <module>
ModuleNotFoundError: No module named 'inbox_poll'
exit 1
```

## inbox eval (branch selftest.py) against origin/main code
```
    import inbox_poll as poll
ModuleNotFoundError: No module named 'inbox_poll'
exit 1
```

## Proof command on the branch
```
exit 0
```

## inbox eval on the branch
```
o/r {'headRefOid': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'createdAt': '2026-11-22T17:18:16Z'}: 'number'
inbox eval ok
exit 0
```
