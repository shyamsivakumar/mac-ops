# MO-1096 proof

## Before: proof command on origin/main c74eb10f
```
0
exit 1
```

## After: same command on the branch
```
2
exit 0
```

## Install plan against a temp HOME and temp coordinator folder
```
["<tmp>/coord/loop/stuck.py", "<tmp>/coord/loop/watch.py"]
```

## stuck.py
```
empty repo list via COORDQ_TICKETS_CONFIG: exit 0
missing config: FileNotFoundError: [Errno 2] No such file or directory: '<tmp>/none.json'
literal /Users/ paths: 0
```
