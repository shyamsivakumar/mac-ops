# MO-1057: the whole tick finishes under 600 seconds when a call hangs

Date: 2026-11-17

The tick is the launcher in `coordinator/pi/bin/coord-tick`. The proof runs
that launcher for real: one of its GitHub calls is pointed at a blackhole of
this machine's own (a listening port that accepts the connection and never
answers, so the call waits with no client timeout of its own), and the agent
turn is stood in for by a script that reads the board, does the rest of its
work and replies.

```
$ /opt/homebrew/bin/python3 evidence/MO-1057/proof.py
```

## The tick

```
    NOOP the board read skipped 8 calls; the other checks ran
    tick exit=0 elapsed=133s
    --- the tick log
    2026-11-17 09:14 PST | tick | overnight selftest: not-due
    2026-11-17 09:18 PST | tick | exit=0 reply=NOOP the board read skipped 8 calls; the other checks ran
    --- the calls the tick skipped
    overnight: skipped /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmptubz6rmq/blackhole/gh issue list -R shyamsivakumar/openscan --state open --limit 500 --json number,title,body after 60s (the call timed out)
    overnight: skipped /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmptubz6rmq/blackhole/gh issue list -R digitized/Concerning --state open --limit 500 --json number,title,body after 60s (the call timed out)
    overnight: skipped /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmptubz6rmq/blackhole/gh issue list -R shyamsivakumar/CineJar --state open --limit 500 --json number,title,body after 60s (the call timed out)
    --- skipped calls: 8
    --- the rest of the tick's work
    the lanes pass and the jobs are alive
    --- the tick finished under 600 seconds: True
    exit=0
```

The whole tick ran in 133 seconds, well inside its 600-second limit. The
hung call was skipped and named, the tick carried on with its other work,
and it replied and exited 0. The tick's log carries the reply:

```
2026-11-17 09:14 PST | tick | overnight selftest: not-due
2026-11-17 09:18 PST | tick | exit=0 reply=NOOP the board read skipped 8 calls; the other checks ran
```

## The board read alone

The same blackhole call, run on its own (`overnight board --json --action`,
the tick's own call):

```
$ OVERNIGHT_GH=$TMPDIR/tick-blackhole.*/bin/gh \
    /opt/homebrew/bin/python3 coordinator/overnight/overnight board --json --action
exit=1 elapsed=128s

# stderr (the skipped calls, one per repository)
overnight: skipped .../bin/gh issue list -R digitized/Concerning --state open --limit 500 --json number,title,body after 60s (the call timed out)
overnight: skipped .../bin/gh issue list -R shyamsivakumar/openscan --state open --limit 500 --json number,title,body after 60s (the call timed out)
overnight: skipped .../bin/gh issue list -R shyamsivakumar/recoup --state open --limit 500 --json number,title,body after 60s (the call timed out)
...
# skipped calls:        8
overnight: REFUSED: the ticket text of these repositories could not be read: digitized/Concerning, shyamsivakumar/CineJar, shyamsivakumar/mac-ops, shyamsivakumar/openscan, shyamsivakumar/recoup, shyamsivakumar/scripture-scroll, shyamsivakumar/strategy-replay-workbench, shyamsivakumar/tunerise
```

The read ends in 128 seconds, well inside the tick's 600 seconds, and every
call it had to skip is named. Before the fix the read had no bound of its
own: its deadline was 540 seconds, 90 percent of the tick's budget, and the
repositories were read one after another, so a stalled GitHub cost a timeout
per repository.

Device, handset and live-service testing was waived by the standing decision
of 2026-11-14; nothing here depends on a device or a live service.
