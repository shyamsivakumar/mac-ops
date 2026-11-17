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

The output of that run is in `tick-proof.out`:

```
    NOOP the board read skipped 8 calls; the other checks ran: lanes: loop/lanes.log age 96s
    tick exit=0 elapsed=126s
    --- the tick log
    2026-11-17 09:38 PST | tick | overnight selftest: not-due
    2026-11-17 09:40 PST | tick | exit=0 reply=NOOP the board read skipped 8 calls; the other checks ran: lanes: loop/lanes.log age 96s
    --- the calls the tick skipped
    overnight: skipped /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmpc1jak674/blackhole/gh issue list -R digitized/Concerning --state open --limit 500 --json number,title,body after 60s (the call timed out)
    overnight: skipped /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmpc1jak674/blackhole/gh issue list -R shyamsivakumar/CineJar --state open --limit 500 --json number,title,body after 60s (the call timed out)
    overnight: skipped /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmpc1jak674/blackhole/gh issue list -R shyamsivakumar/mac-ops --state open --limit 500 --json number,title,body after 60s (the call timed out)
    --- skipped calls: 8
    --- the rest of the tick's work, read for real
    lanes: loop/lanes.log age 96s
    dispatch: last write age 4s
    overnight: log age 10s
    traceback: dispatch 0
    gatekeep: traceback 0
    launchd: dev.coordinator.lanes state = not running
    decisions: 1 item(s)
    read at 2026-11-17 09:40 PST
    --- the checks that ran after the hung call: 5
    --- the tick finished under 600 seconds: True
```

## What the receipt shows

- The whole tick ran in 126 seconds, well inside its 600-second limit, and
  it exited 0.
- The hung call was skipped and named: eight `overnight: skipped ...` lines,
  one per repository, each with the command that was skipped and the 60
  seconds it was given. The skips are also written to
  `~/Library/Logs/coordinator/skips.log`, so they do not depend on a model
  repeating them.
- The tick's other work ran after the hung call and read real values: the
  lane driver's log age (`loop/lanes.log`, the file `loop/tick.md` names),
  the dispatcher's last write, the shift's log age, the tracebacks in the
  last lines of the two queue logs, the state of the launchd job and the
  decisions log. Those checks are `evidence/MO-1057/other_work.py`, and
  they read the live files; nothing in the receipt is written by hand.
  The proof fails when those checks do not run or do not measure: it
  counts the lines that carry a measured value, and it needs four of
  them, so a stand-in that only claims to have run them does not pass.

The board read on its own, with the same blackhole call, ends in 128 seconds
with the same eight skips (`blackhole-proof.md`).

Device, handset and live-service testing was waived by the standing decision
of 2026-11-14; nothing here depends on a device or a live service.
