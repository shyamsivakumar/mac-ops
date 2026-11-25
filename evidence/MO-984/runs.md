# MO-984 runs

## Ticket proof, origin/main then head

Proof command:

```text
HOME=/nonexistent python3 -c "import runpy,sys;sys.path.insert(0,'coordinator/bin');s=runpy.run_path('coordinator/bin/coordq',run_name='p');r=lambda n,o:{'number':n,'labels':[{'name':'stage:todo'}],'body':'','repository':{'nameWithOwner':o}};got=[x['number'] for x in s['lane_candidates']([r(1,'o/a'),r(2,'o/a'),r(3,'o/b')],set(),{},())];print('candidates',got);sys.exit(got!=[1,3,2])"
```

origin/main (archive of 5574760f):

```text
candidates [1, 3]
exit 1
```

head:

```text
candidates [1, 3, 2]
exit 0
```

## refill-busy eval with the new assertions, run against origin/main code

```text
AssertionError: expected [673, 674, 675, 676, 677, 678, 679, 680, 681], got [673]
```

On the head the `refill-busy` and `build-here` evals pass.

## Read-only run over the live board

`board_candidates()` with a temp COORDQ_DIR (copies of queue.json and the receipts file), a
temp copy of tickets.json and the real GitHub and T3 reads. Nothing was started or written.
Active lanes at the time of the run: SRW#1619, tunerise#117, scripture-scroll#52.

```text
lanes unset (all repos):        offered: {}
SRW lanes 2:                    offered: SRW [1646, 2356, 2358, 2371, 2548, 2566, 2549, 2542, ...]
SRW and STS lanes 2:            offered: SRW [...same...], scripture-scroll [40, 45]
```

STS#52 held its lane during this run, so STS offers #40 and #45 only with `lanes` 2.
