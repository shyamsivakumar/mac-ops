# MO-933 runs

Code commit: 5421f6285351d6a4264ee2d1aa1a66a688bc7c26. The ticket's "first multiple of its period after now" is read as multiples counted from due_ts, so the next due time is strictly after now and stays on the timer's own grid.

Proof command is the ticket's, run as a file (same statements). Case that fails on main and passes on the branch: the `inbox` eval of coordinator/overnight/selftest.py.

## origin/main (b9954b96) with the new selftest
```
$ proof
    import os,sys,tempfile;os.environ['COORD_INBOX_DIR']=tempfile.mkdtemp();sys.path.insert(0,'coordinator/bin');import inbox;inbox.add_timer('t1',due_ts=100.0,period=50.0);assert inbox.enqueue_due_ti
AttributeError: module 'inbox' has no attribute 'add_timer'
exit 1
$ eval
    store.add_timer("t1", due_ts=100.0, period=50.0)
AttributeError: module 'inbox' has no attribute 'add_timer'
exit 1
```

## branch at the code commit
```
$ proof

exit 0
$ eval
inbox ok
exit 0
```

## Fast check (M1)
```
Checked commit: `5421f6285351d6a4264ee2d1aa1a66a688bc7c26`
Run result: passed
```
