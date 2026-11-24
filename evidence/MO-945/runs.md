# MO-945 runs

## Ticket proof command (installed_selftest on archives of d5efd3f8 and b9954b96)

### On origin/main 9735d513
```
AttributeError: module 'mac_ops_fast_check' has no attribute 'installed_selftest'
```
### On the head (code commit 03e057d3)
```
(False, "FAIL inbox: [Errno 2] No such file or directory: '<tmp>/home/scripts/coord_wake_metrics.py'")   d5efd3f8
(True, 'exit 0, 34 PASS')                                                                                b9954b96
exit 0
```
The eval that fails flat on d5efd3f8 is `inbox`, reading `scripts/coord_wake_metrics.py`.

## Nothing outside the temp dir is written

Names and mtimes (no contents) of every path under `~/.local/bin`, `~/.coordinator` and `~/.pi/agent-coordinator` (93340 lines) were listed before and after two runs of the proof command.

| Window | Result |
| --- | --- |
| Run 1 (65 s) | identical except the mtime of the directory `~/.pi/agent-coordinator` itself (1795537881 to 1795539992, 12:06:32); no child file changed; 5 other `pi` processes were live on this Mac |
| Control, 65 s with nothing of ours running | identical |
| Run 2 (65 s) | identical |

Run 1's directory mtime is not reproduced by run 2 and `installed_selftest` never names that path; the cause is not established. `plan()` only reads (os.access, rglob, exists) and runs in a subprocess started with `-B` and no HOME.

## Time added

One `installed_selftest(Path("."))` on this head: 33.8 s wall (real 33.77). The ticket limit is about 60 s.

## Fast check on the M1

`scripts/remote_fast_check.sh --remote mo945-installed-selftest 03e057d3... evidence/MO-945/check-proof.md`: `fast-check: passed`; the proof row reads `installed selftest | passed | exit 0, 34 PASS`, host Shyams-MacBook-Pro.local.
