---
name: verify-restart-latch
description: Verify the board restart watcher restarts one agent exit only once after changing board_restart.py or the controller's restart tick.
---

# Verify the board restart latch

Run this after changing `board_restart.py` (`tick`, `restart`,
`read_state`, `write_state`) or `board_governor.py`
(`_board_restart_tick`, the `agent_restart` branch of `controller_tick`).

## Property

One death of an agent, identified by `exitedAt`, is handed to the next
model once, after the watcher has replaced its state file with that exit
saved. A missing exit time or a rejected state file restarts nothing. If
the new agent comes up, the tell is sent. This is serialized ticks whose
writes complete. It is not a promise across a crash between the board
commands and `os.replace`.

A second restart repeats `stop` / `archive` / `restore` / `delegate` on
work already handed on. It also uses up the three restarts allowed for
that task in an hour.

## What the check proves

`formal/restart/RestartLatch.tla` is one task, two exit identities, and
at most three restart attempts. `SafetySpec` explores every tick in that
bound, including a newer exit, a failed command, a healthy row, the same
exit coming back, a missing exit, and a rejected state file.
`RestartLatch.cfg` passes `NoDoubleSuccess`, `NoActionOnBadInput`, and
`SavedLatch`. `RestartLive.cfg` uses `LiveSpec`: weak fairness on seeing
the row, aging the 60 second clock, a successful restart, the agent
coming up, and the tell. It passes `EventuallyRestarted` and
`EventuallyTold`.

A pass covers that model only. `exitedAt` does not move backward: a
missing time remembers the exit that was just showing, and the next
number is that exit or a newer one. It does not cover two tasks at once,
the board-wide cap of six, the 90 second freshness wait (the model starts
after the exit is old enough), machine-wide start failures, the order of
fallback models, or a crash between the board commands and `os.replace`.

## Covered code and sync

- `board_restart.py`: `classify` (`agent_exited`), `tick` (tell, missing
  `exitedAt`, `restarted_exit`, interval, caps, success and failure),
  `read_state`, `write_state`
- `board_governor.py`: `_board_restart_tick`, and the `agent_restart`
  branch of `controller_tick` that catches a watcher error
- Sync commit: 2371483d89697adea29ede655c195e4a77bcda92
- Move the sync commit only after the model still matches those lines
  and the check script has run at the new commit.

| Action | Code |
| --- | --- |
| `See`, `Age` | `tick` signature, `first_seen`, interval check |
| `RestartOk` | `restart()` ok, then `restarted_exit`, `write_state` |
| `RestartFail` | a failed step, no `restarted_exit`, attempt counted |
| `Tell` | `pending_tell` and `agent_is_up` |
| `Missing`, `Corrupt` | non-numeric `exitedAt`; `read_state` raises |
| `NewDeath` | same signature, new `exitedAt`, `first_seen` kept |
| `GoHealthy` | row leaves dead signatures; `restarted_exit` stays |
| `Recover` | the exit that left the row returns; `exitedAt` never moves back |

`Persist = FALSE` is the crash after `restart()` and before
`os.replace`. The next tick reads the old file. That is a real path.
`RestartCrash.cfg` violates `NoDoubleSuccess`. Do not treat that
configuration as a pass.

## Command

From the mac-ops repo root, one heavy run:

```bash
heavy /bin/bash formal/restart/check.sh
```

The script copies the model into `$TMPDIR` and runs TLC with one worker
and a 512 MiB heap. Java is `/opt/homebrew/opt/openjdk@17/bin/java`.
The jar is
`/Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar`.

| Config | Result |
| --- | --- |
| `RestartLatch.cfg` | pass, with coverage |
| `RestartLive.cfg` | pass, including both liveness properties |
| `RestartReach.cfg` | must violate `NotYetRestarted` (success reachable) |
| `RestartNoLatch.cfg` | must violate `NoDoubleSuccess` |
| `RestartCrash.cfg` | known gap: must violate `NoDoubleSuccess` |
| `RestartWipe.cfg` | must violate `SavedLatch` |
| `RestartBadInput.cfg` | must violate `NoActionOnBadInput` |

The script also runs `formal/restart/replay_latch.py` on `tick`. The same
exit restarts once, a newer exit restarts once, a failed command retries,
and the tell is sent without a second restart. A copy of
`board_restart.py` with the `restarted_exit` lines removed must restart
the same exit twice. A `write_state` error after the commands must still
restart again; the script prints that as `KNOWN GAP`. The lifetime cap of
three in the model is stricter than the code's rolling hour, and the
repeated restart happens on the second attempt, so the cap does not hide it.

Raw output stays under `$TMPDIR`. Quote the state count and depth from that output.
`WipeFile` shows `0:0` in the `RestartLatch` coverage because that config
sets `Wipe = FALSE`. `RestartWipe.cfg` is the run that reaches it.

## Tell a bug from a modeling error

Replay the trace with `tick` in dry-run, passing rows, panes, and task
meta yourself. Do not call the live board.

1. Same `exitedAt` on three ticks a minute apart, pane still the old
   session: the third tick must not restart.
2. Same row, and on the third tick the pane session has changed: the
   third tick tells and does not restart.
3. A newer `exitedAt` already 90 seconds old: one more restart.
4. The first `restart()` step fails: the exit is not saved, and the next
   tick retries.
5. `exitedAt` missing: no restart.
6. `write_state` raises after a successful dry-run restart: the next
   tick restarts again. That is the crash finding. The latch cannot fix
   it, because the latch is written in the file the crash skips.

If a TLC step cannot be done by `tick`, the model is wrong. If every
step can, it is a bug in the watcher.

## When the code changes

A new branch in `tick` that can call `restart()` has to become an
action, with the file and line on its guard. Change `NoDoubleSuccess`
only when the commit, the chart, or the tests say the promise changed.
Then move the sync commit.
