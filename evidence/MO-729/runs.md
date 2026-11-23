# MO-729 runs

Proof command (SRW #1498 shape: gate PASS on the head, ticket not in the open snapshot, closed as completed by another PR; plus a not-planned close that still holds):

```
python3 -c "import os,sys,runpy,tempfile;os.environ['COORD_JOURNAL_DIR']=tempfile.mkdtemp();sys.path.insert(0,'coordinator/overnight');m=runpy.run_path('coordinator/overnight/selftest.py',run_name='st');m['closed_ticket_merge']();print('closed-ticket-merge ok')"
```

## origin/main (8c0b1568) with the new case copied in: red

```
  File "coordinator/overnight/selftest.py", line 4452, in closed_ticket_merge
    exact((merges, items), ([""], []))
AssertionError: expected ([''], []), got ([], [])
rc=1
```

The completed-ticket PASS head reaches no merge.

## head: green

```
closed-ticket-merge ok
rc=0
```

The case asserts: completed ticket + PASS merges with the ticket close skipped (issue passed as empty);
not planned + PASS merges nothing and raises one board item per head (a second pass adds none);
completed + no PASS is not gated or sent fixes; an unreadable ticket is skipped with a reason; a dry run writes no item.

## Not run

Acceptance item 3 (dry lane pass on the real SRW snapshot) was not run: builders may not run the lane.
