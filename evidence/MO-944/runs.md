# MO-944 runs

Proof command is the one in the ticket, run from the repo root with a temporary HOME.

## Ticket proof on origin/main (red)
```
AttributeError: module 'cq' has no attribute 'scope_refusal'
exit 1
```

## close-evidence eval with the new cases on origin/main code (red)
```
AttributeError: module 'fixture_coordq' has no attribute 'scope_refusal'
exit 1
```

## Ticket proof on the branch (green)
```
exit 0
```

## close-evidence eval on the branch, flat copy of coordinator/bin and coordinator/overnight (green)
```
close-evidence OK
exit 0 (prints close-evidence OK)
```
