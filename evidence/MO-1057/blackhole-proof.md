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

## The whole tick, with the hung call, under 600 seconds

The receipt above is the board read on its own. The tick's own receipt is the
launcher run for real, with the same blackhole call and a stand-in for the
agent turn that reads the board, writes its other work and replies:

```
$ /opt/homebrew/bin/python3 evidence/MO-1057/proof.py
tick exit=0 elapsed=126s
--- the tick log
2026-11-17 09:19 PST | tick | overnight selftest: not-due
2026-11-17 09:21 PST | tick | exit=0 reply=NOOP the board read skipped 8 calls; the other checks ran
--- the calls the tick skipped
overnight: skipped .../blackhole/gh issue list -R digitized/Concerning ... after 60s (the call timed out)
overnight: skipped .../blackhole/gh issue list -R shyamsivakumar/mac-ops ... after 60s (the call timed out)
overnight: skipped .../blackhole/gh issue list -R shyamsivakumar/CineJar ... after 60s (the call timed out)
--- skipped calls: 8
--- the rest of the tick's work
the lanes pass and the jobs are alive
--- the tick finished under 600 seconds: True
```

The receipt is `evidence/MO-1057/tick-proof.out`. The tick exits 0 in 126
seconds with its model check bounded, the hung board read skipped and named,
and the rest of its work done: the hung call costs the tick one timeout and
not the tick. The stand-in answers the launcher's model check itself and
points only the board read's `gh` at the blackhole, the way the read of
2026-11-17 hung, so the sandboxed `pi` call path is the real one.

## A descendant cannot outlive the call

A call runs in a process group of its own, and the group is emptied after the
leader is gone, not only when the wait ends: a descendant that ignores SIGTERM
and closes or redirects its output would otherwise keep running behind the
tick, and the escalation would never happen. That end is one helper per file,
`end_group` in `overnight` and in `coord-tick`, used by every bounded call,
the model check, and the tick's long run. `tests/test_tick_external_call_bounds.py`
covers it for the call helper and for the run the tick kills:

```
$ python3 -m unittest tests.test_tick_external_call_bounds
Ran 8 tests in 19.1s
OK
```
