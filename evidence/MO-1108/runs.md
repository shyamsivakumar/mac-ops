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

## Gate finding: STOP or policy changing during the wait
`act` now checks STOP and the repository's policy again after the lock is taken, right before `act_on_pr`. The case `overnight_act` gains a run where STOP appears while the watcher waits for the gate thread.
Before the fix (head 0296b297): the case fails, `act_on_pr` ran (`expected (0, []), got (0, [(repo, 7)])`).
After: the case passes and nothing is acted on.
