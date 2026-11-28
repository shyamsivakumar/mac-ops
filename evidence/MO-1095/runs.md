# MO-1095 proof

## Ticket proof command on origin/main (red)
```
1
exit 1
```

## Ticket proof command on this branch (green)
```
0
exit 0
```

## Selftest case close-evidence (3 fake heads, proofsPerRun 2)

On origin/main code with this selftest: AssertionError expected ((2, 2), (3, 1), [a, b, c]), got ((1, 1), (2, 1), [a, b]).

```
PASS close-evidence
```
