# MO-783 runs

Proof command, run in the worktree (path passed as argv; the ticket's command is the same code with the path fixed). Branch is based on #796 (MO-763) because check_body is not on main yet.

## Before (base commit c1204c75, without the change)
```
KeyError: 'scope_files'
```

## After (branch)
```
['coordinator/bin/coordq']
```

## ticket start --dry-run with stubbed gh (temp COORDQ_DIR, COORD_JOURNAL_DIR, HOME)
Ticket 101 is stage:started and names coordinator/bin/scorecard. Ticket 102 shares it; ticket 103 does not.
```
$ ticket start #102 --dry-run (101 started)
refused: overlaps #101 on coordinator/bin/scorecard
exit 2
$ ticket start #103 --dry-run (101 started)
checks passed
intent comment:
Starting MO-103 attempt 1. Builder: terra, reviewer: opus-api.

exit 0
$ ticket start #102 --dry-run (nothing started)
checks passed
intent comment:
Starting MO-102 attempt 1. Builder: terra, reviewer: opus-api.

exit 0
$ ticket start #102 --dry-run (101 started), base code
checks passed intent comment: 
```

Journal row written by the refused start:
```
{"v":1,"ts":1795213033.843449,"event":"start_deferred","actor":"ticket","repo":"shyamsivakumar/mac-ops","ticket":102,"pr":null,"head":null,"thread":null,"item":null,"attempt":null,"kind":null,"data":{"overlaps":[{"ref":101,"path":"coordinator/bin/scorecard"}]}}
```
