# MO-1057: the tick's external calls are bounded

Date: 2026-11-17

The proof of the whole tick, with one of its GitHub calls hung, is in
`tick-proof.md`. This file holds the board read on its own, which is the
call the tick makes.

One call of the tick's board read is pointed at a blackhole address:

```
$ cat $TMPDIR/tick-blackhole.*/bin/gh
#!/bin/sh
# A GitHub call pointed at a blackhole address: the connect never answers.
exec /usr/bin/curl -sS --connect-timeout 600 http://10.255.255.1/github
```

The read is the one the tick runs: `overnight board --json --action`.

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
repositories were read one after another, so a stalled GitHub cost a
timeout per repository.
