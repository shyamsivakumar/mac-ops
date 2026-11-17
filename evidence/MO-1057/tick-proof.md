# MO-1057: the whole tick finishes under 600 seconds when a call hangs

Date: 2026-11-17

The tick is the launcher in `coordinator/pi/bin/coord-tick`, and the proof
runs the real thing: the real `pi`, the real coordinator config, the real
prompt of the launcher, on the coordinator's own tick model. Nothing stands
in for the agent.

One of the tick's GitHub calls is pointed at a blackhole of this machine's
own: a listening port that accepts the connection and never answers, so the
call waits with no client timeout of its own. The launcher's log, lock and
skip log are moved to a scratch folder, and the repository's own
`overnight` is put first on the tick's PATH, so the tick runs the code of
this branch.

```
$ /opt/homebrew/bin/python3 evidence/MO-1057/proof.py
```

The output of that run is in `tick-proof.out`:

```
    Tick done at 10:09 PT. No alarm of the three kinds, so no `ALERT:` line.
    
    **Named hang:** `overnight board --json --action` hung past my 120 s shell bound. Skipped, not retried, so board counts came from `loop/stuck.py` plus direct `gh` reads. This is the same class of failure mac-ops PR #486 exists to fix.
    
    **One action:** SRW#1251 (SRW-1186). Refill refused it at 10:03:40 as "already merged via #1259; close the issue" while the board called it ready. PR #1259 merged the crash handling but its body lists the ticket's own acceptance items as "Left for later": the failing sanitized export and before/after replay, the #1244 lock and #1247 TLA+ receipts, and the 12:00 one-record-per-run ledger check. The gate merged on a standard bar while the ticket names the full proof bar. I posted a Coordinator restart comment ([issuecomment-6956565881](https://github.com/shyamsivakumar/strategy-replay-workbench/issues/1251#issuecomment-6956565881)) with the bounded attempt 5 as evidence-only work. `ticket start ...#1251 --dry-run` now prints attempt 5 from origin/main where it printed the refusal. I did not close the ticket, and I did not start it: slots are 6 of 6 with refill owning the start.
    
    **Left alone:** recoup#41 (ORPHAN, label-less, but its builder thread is running), mac-ops#482 (label-less, open PR #486 with a live builder at head efac9d4b), everything on `stage:hold`.
    
    **Counts:** 22 open tickets (SRW 1, mac-ops 1, scripture-scroll 1, CineJar 2, openscan 5, recoup 5, tunerise 5, Concerning 2), 15 open PRs, 19 merged today.
    
    **Drift logged, not fixed (freeze):** gatekeep queued four gates for PR #486 at four heads and the current head has none; CineJar holds 7 open PRs for 2 tickets; `ticket start` still prints an opus reviewer for type:risky; interrupted builders leave tickets with no stage label, which refill cannot see.
    tick exit=0 elapsed=280s
    --- the tick log
    2026-11-17 10:00 PST | tick | overnight selftest: not-due
    2026-11-17 10:05 PST | tick | exit=0 reply=Tick done at 10:09 PT. No alarm of the three kinds, so no `ALERT:` line.
    
    **Named hang:** `overnight board --json --action` hung past my 120 s shell bound. Skipped, not retried, so board counts came f
    --- the calls the tick skipped
    2026-11-17 10:01 PST | skipped | /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmp0c7wskp4/blackhole/gh issue list -R shyamsivakumar/mac-ops --state open --limit 500 --json number,title,body after 60s
    --- skipped calls: 1
    --- the tick finished under 600 seconds: True
```

## What the receipt shows

- The whole tick ran in 280 seconds, well inside its 600-second limit, and
  it exited 0.
- The hung call was skipped and named by the tick itself. The agent's own
  reply says so: "**Named hang:** `overnight board --json --action` hung past
  my 120 s shell bound. Skipped, not retried, so board counts came from
  `loop/stuck.py` plus direct `gh` reads." The launcher logged the reply in
  its log, and the skip is in `~/Library/Logs/coordinator/skips.log`:
  `skipped | .../blackhole/gh issue list -R shyamsivakumar/mac-ops --state
  open --limit 500 --json number,title,body after 60s`.
- The agent carried on with the rest of the tick's work after the hung
  call: it read the board another way, ran the tick's own checks, posted
  the coordinator comment its board called for, and reported the counts and
  the drift in its reply.

The board read on its own, with every repository's call hung, ends in 128
seconds with the eight skips named (`blackhole-proof.md`).

Device, handset and live-service testing was waived by the standing decision
of 2026-11-14; nothing here depends on a device or a live service.
