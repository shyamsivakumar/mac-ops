# MO-1033 (#1033): slow headless turn alarm keyed to ticks.log

## Format finding

Tick lines in `~/Code/coordinator/loop/ticks.log`
(`2026-11-27 07:00 ET | tick (launchd) | ...`) have a finish time, no duration.
Only rows from `coordinator/overnight/turn_cap.py` have a duration.
It appends them for a headless run over the limit:

    - cap mis-sized <ts> | <harness> | <title> | <run id> | <N> min
    - cap hit <ts> | <harness> | <title> | <run id> | <N> min

`cap mis-sized` is written once past 10 min.
`cap hit` is written past 20 min, when the run is interrupted.

The alarm keys on those rows. One run writes both, so it fires once per run id.
The limit is `limits.slowTickMinutes` in the config coord-watch already loads
(default 10, the slowness-is-a-bug trigger).

## Proof command

Run in a directory with these fixtures:

- `cfg.json` has `limits.slowTickMinutes` = 10.
- `ticks.log` has a 10.5 min run that later hits 20.8 min, a 6.2 min run,
  and a normal tick line.

Command:

    python3 coordinator/bin/coord-watch --once --fake-input raw.json \
        --config cfg.json --state state.json --log ticks.log | grep -v '^BOARD'

`raw.json` is `{"github":{},"threads":[],"threadsComplete":true,"queue":{"queue.json":{"items":[]},"dispatch-receipts.json":{},"log":""}}`.

## origin/main (ec62b5e0)

Cycle 1 output: nothing. Cycle 2 output: nothing. (No slow-tick alarm exists.)

## Branch

Cycle 1 printed exactly one alarm, for the 10.5 min run.
Its 20.8 min `cap hit` row is deduped by run id. The 6.2 min run is silent.

<!-- markdownlint-disable MD013 -->

    EVENT slow-tick 10.5min limit=10 SRW-1994  Bot 2 two-lane  Apply reservations | fix it per ~/.claude/skills/slowness-is-a-bug/SKILL.md, then log: slow-turn 2026-11-27 SRW-1994  Bot 2 two-lane  Apply reservations | slowest step: <step> <seconds before> | fix: <one phrase> | after: <seconds> | spent: <minutes> | saved per run: <seconds> | runs per week: <n> | kept|reverted

<!-- markdownlint-enable MD013 -->

Cycle 2 on the same state file: nothing (once per run id).

Config read: the same fixture with `slowTickMinutes` = 30 prints no alarm.

## Real data

Input was a copy of the live ticks.log (1803 lines), fresh state, two cycles.
origin/main printed 0 slow-tick events. The branch printed 64.
The first 64 KB chunk held no cap rows; the second chunk held them.
The existing reader consumes 64 KB per cycle.
An install replays the old backlog once over a few cycles.
After that, only new rows alarm.
