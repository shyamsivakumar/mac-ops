# MO-810 runs

Real file lists read-only with gh pr view (SRW 1563, 1567, 1575, 1579; mac-ops 808). Temp COORDQ_DIR, COORD_JOURNAL_DIR, HOME. The two fake cases are a 615-line PR, without and with the gate:whole label.

## size_class on origin/main
```
1563: (706, 4) recut
1567: (547, 5) recut
1575: (583, 3) recut
1579: (1812, 8) recut
808: (3652, 24) recut
fake 615 lines, no label: recut
fake 615 lines, gate:whole: n/a
```

## size_class on the head
```
1563: (80, 3) ok
1567: (208, 4) over_cap
1575: (220, 2) over_cap
1579: (798, 4) recut
808: (127, 2) ok
fake 615 lines, no label: recut
fake 615 lines, gate:whole: over_cap
```

## gate_candidates with a recutHeads entry (gh stubbed; a skip line means the head was judged again)

origin/main, WHOLE= (no gate:whole handling):
```
no label None -> judged again
no label {'at': 1} -> skipped (recut entry honoured)
no label {'at': 1, 'rule': 0} -> skipped (recut entry honoured)
```
head, WHOLE=:
```
no label None -> judged again
no label {'at': 1} -> judged again
no label {'at': 1, 'rule': 2} -> skipped (recut entry honoured)
```

origin/main, WHOLE=1 (no gate:whole handling):
```
label None -> judged again
label {'at': 1} -> skipped (recut entry honoured)
label {'at': 1, 'rule': 0} -> skipped (recut entry honoured)
```
head, WHOLE=1:
```
label None -> judged again
label {'at': 1} -> judged again
label {'at': 1, 'rule': 2} -> judged again
```

## recut card withdrawal (alarms.route_update raise then remove, temp board)
```
raise wrote
board ['recut-fft-533']
remove wrote
board []
```
