# MO-938 runs

Ticket proof command (script form of the ticket body), HOME=/nonexistent. Code commit b6b8d6de8b0f84fb0b4c0814d08db7aecc66e1f5.

## origin/main modules (red)
```
AttributeError: module 'inbox_outbox' has no attribute 'request_notice'
exit 1
```

## head (green)
```
exit 0
```

## inbox eval of coordinator/overnight/selftest.py
```
origin/main modules + head selftest.py:
AttributeError: module 'inbox_outbox' has no attribute 'request_notice'
exit 1
head, PYTHONPATH=coordinator/bin:
exit 0
head, flat copy of coordinator/bin/*.py + coordinator/overnight/*.py in a temp dir:
o/r: skipped a malformed pull request
exit 0
```
