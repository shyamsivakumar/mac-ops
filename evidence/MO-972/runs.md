# MO-972 runs

## Ticket proof on origin/main (a15ec9cd)
```
  File "<string>", line 1, in <module>
KeyError: 'held_merge'
exit 1
```

## held-merge eval on origin/main coordq
```
    ask = lambda key="", title="", rows=rows: coordq.held_merge(key, title, rows, keys)
AttributeError: module 'fixture_coordq' has no attribute 'held_merge'
exit 1
```

## Ticket proof on the branch
```

exit 0
```

## held-merge eval on the branch (real cmd_start, temp queue and journal)
```
held-merge ok
exit 0
```

## After review fixes (key and title both checked, KEY#n and on PASS forms)
```
held-merge ok
exit 0
```
