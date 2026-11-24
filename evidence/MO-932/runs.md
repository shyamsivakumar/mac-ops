# MO-932 runs

## Proof command on origin/main (red)
```
  File "<string>", line 1, in <module>
ModuleNotFoundError: No module named 'inbox_replay'
```

## Proof command on the branch (green)
```
exit 0
```

## inbox eval of coordinator/overnight/selftest.py, case inbox() including replay_cases()

origin/main bin with the branch selftest:
```
ModuleNotFoundError: No module named 'inbox_replay'
```
branch:
```
inbox eval ok
```
