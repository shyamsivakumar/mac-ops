# MO-938 runs

Proof command (ticket body) as a script, HOME=/nonexistent.

## origin/main modules (red)
```
AttributeError: module 'inbox_outbox' has no attribute 'request_notice'
exit 1
```

## head (green)
```
(no output)
exit 0
```

## inbox eval of coordinator/overnight/selftest.py (head selftest.py)
```
origin/main modules:
AttributeError: module 'inbox_outbox' has no attribute 'request_notice'
head:
inbox eval ok
```
