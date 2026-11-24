# MO-933 runs

## origin/main (b9954b96) with the new selftest
```
$ proof command
  File "<string>", line 1, in <module>
AttributeError: module 'inbox' has no attribute 'add_timer'
exit (see output)
$ inbox eval
  File "/private/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmp.wPn7vxgOqF/coordinator/overnight/selftest.py", line 4516, in timer_cases
    store.add_timer("t1", due_ts=100.0, period=50.0)
AttributeError: module 'inbox' has no attribute 'add_timer'
exit (see output)
```

## branch
```
$ proof command
exit (see output)
$ inbox eval
inbox ok
exit (see output)
```
