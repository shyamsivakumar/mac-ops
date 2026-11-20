# MO-810 runs

Real file lists read-only with gh pr view (SRW 1563, 1567, 1575, 1579; mac-ops 808). Temp COORDQ_DIR, COORD_JOURNAL_DIR, HOME.

## size_class on origin/main
```
1563: (706, 4) recut
1567: (547, 5) recut
1575: (583, 3) recut
1579: (1812, 8) recut
808: (3652, 24) recut
```

## size_class on the head
```
1563: (80, 3) ok
1567: (208, 4) over_cap
1575: (220, 2) over_cap
1579: (798, 4) recut
808: (127, 2) ok
```

## gate_candidates with a recutHeads entry (gh stubbed; a skip line means the head was judged again)

origin/main:
```
None -> judged again
{'at': 1} -> skipped (recut entry honoured)
{'at': 1, 'rule': 0} -> skipped (recut entry honoured)
```
head:
```
None -> judged again
{'at': 1} -> judged again
{'at': 1, 'rule': 2} -> skipped (recut entry honoured)
```
