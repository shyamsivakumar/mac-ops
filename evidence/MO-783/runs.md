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

## ticket start with stubbed gh (temp COORDQ_DIR, COORD_JOURNAL_DIR, HOME)
Ticket 101 is stage:started and names coordinator/bin/scorecard. Each run has its own empty journal dir. The refused real start stops before any comment, label or coordq call; the stub answers no write.
```
$ ticket start #102 --dry-run (101 started): refused, journal unchanged
refused: overlaps #101 on coordinator/bin/scorecard
exit 2; journal rows:        0
$ ticket start #102 (101 started, not a dry run): refused, one start_deferred row
refused: overlaps #101 on coordinator/bin/scorecard
exit 2; journal rows:        1
{"v":1,"ts":1795213247.1746602,"event":"start_deferred","actnull,"item":null,"attempt":null,"kind":null,"data":{"overlaps":[{"ref":101,"path":"coordinator/bin/scorecard"}]}}
$ ticket start #103 --dry-run (disjoint): passes
checks passed
intent comment:
exit 0; journal rows:        0
$ ticket start #102 --dry-run (nothing started): passes
checks passed
intent comment:
exit 0; journal rows:        0
Retry of 101 itself, open PR #110 "Refs #101" changes the same file: passes
$ ticket start #101 --dry-run (attempt 2)
checks passed
intent comment:
exit 0; journal rows:        0
Same PR but it refers to #999: refused
$ ticket start #101 --dry-run
refused: overlaps #110 on coordinator/bin/scorecard
exit 2; journal rows:        0
```
