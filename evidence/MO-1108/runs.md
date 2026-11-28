# MO-1108 proof runs

## Ticket proof command on origin/main (red)
```
overnight: error: argument command: invalid choice: 'act' (choose from 'intake', 'filter', 'check-pr', 'order', 'board', 'report', 'shift', 'policy', 'attend', 'receipt', 'budget', 'park', 'close', 'check-head', 'redact', 'turncap', 'board-integrity', 'script-results', 'script-run', 'selftest', 'stall')
```
## On the branch (green)
```
usage: overnight act [-h] [--after AFTER] [--wait WAIT] [--root ROOT] ref

positional arguments:
```
## Selftest case overnight_act (temp dirs, fakes, no heavy)
```
overnight_act ok: waits for the thread (2 reads), acts on exactly the one PR; STOP and a held lock act on nothing
```
## origin/main against the case
```
AttributeError: module 'overnight_runner' has no attribute 'cmd_act'
```
