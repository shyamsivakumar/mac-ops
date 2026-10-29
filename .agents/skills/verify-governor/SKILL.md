---
name: verify-governor
description: Use when changing the mac-ops capacity controller, board slot policy, heavy admission, or critical pause requests.
---

# Verify the capacity governor

Run the check for the policy surface you changed. Both runners use the pinned
TLC jar, one worker, a 512 MiB heap, and a task-`TMPDIR` copy of the model so
counterexample traces stay out of the worktree.

From the repository root, run each needed batch under its own heavy gate:

```bash
heavy --review /bin/bash formal/governor/check.sh
heavy --review /bin/bash formal/governor/check-board-floor.sh
```

The first runner checks heavy slot sizing, admission, and critical pause
behavior. The second runner is the current proof for `board.agents` floor and
growth policy. Do not use the first model's board assertions as evidence for
the current adaptive board floor.

## Heavy capacity and admission model

The model follows `board_governor.py` `_adaptive_capacity_decision`,
`_capacity_decision`, `controller_tick`, and `_board_control_tick`. It follows
`heavy.py` `_read_capacity_config`, `_effective_slot_limit`, `_reserve_job`,
`_launch_job`, `request_critical_pauses`, and the supervisor pause path.

`Governor.tla` checks ceilings 2–4, a floor of `min(2, ceiling)`, fresh and
invalid readings, critical pressure, queue admission, native start success or
failure, critical pause request ordering, pause signal success or failure,
restart, reboot, and expiry. Resource fit uses guard-equivalent values; raw
sensor parsing is not proved. The model preselects one eligible queue entry and
does not explore competing queues, ten-minute aging, deploy priority, or the
one-active-deploy limit.

Its board submodel uses a fixed two-active-task snapshot and is historical; it
does not represent the current `board.agents` floor. The model uses two abstract
healthy steps for the 60 second heavy growth window and one host sample for
both controller publication and admission. The source-mapped chart is in
`docs/state-charts/governor.md`.

`GovernorSafety.cfg` checks the combined heavy invariants.
`GovernorConditionalLiveness.cfg` proves queue start and healthy-window growth
with recurring fresh healthy input, sufficient resources, successful
publication, valid native identity, a free task slot, and a successful native
launch. The `GovernorLegacy*.cfg` configurations preserve the old zero-floor
and no-start counterexamples. The strict missing-reading configurations show
why “no critical signal” alone cannot guarantee a floor or start. Strict
publication and start configurations preserve their corresponding failure
counterexamples. Raw output remains under task `TMPDIR`.

## Current board floor and growth model

`BoardFloor.tla` is the current proof for `_board_control_tick`. With six active
agents, its board floor is `min(ceiling, max(6, active + 1))`; at a ceiling of
at least seven this is seven. A fresh valid noncritical sample restores that
floor in the same tick, including a warning sample, without waiting for the
growth window. Missing, stale, and bad samples cannot raise the limit. A
classified critical sample targets zero. Sample extraction, raw sensor parsing,
and the adapter that preserves known partial critical readings are inputs to
this model, not properties proved by it.

| TLA action | `board_governor.py` correspondence |
| --- | --- |
| `CaptureReading` | Sample, census, prior state: 814-918 |
| `DecideTarget` | Floor, warning, invalid, growth: 913-969 |
| `RecheckAccepted`, `RecheckRejected` | Rechecks: 1002-1024 |
| `WriteSuccess`, `WriteFailure` | Setter, readback: 1024-1030 |
| `StartQueuedJob`, `StartFailure` | External scheduler consuming the limit |

The model abstracts the pre-write board recheck as accepted or rejected.
Acceptance means the board limit and active identities remain the sampled
values, the host sample remains fresh, and the board I/O stays within budget.
A successful floor write is a separate transition from the external scheduler
starting a queued agent. The floor liveness check assumes both the recheck and
write succeed; strict configurations show counterexamples for failed recheck,
failed write, and failed native start.

`Window == 2` represents two abstract 30-second healthy intervals. `growthFits`
means both pending memory and CPU budgets fit the candidate count; raw memory
parsing is not explored. The model starts with six active agents and one
eligible queued agent. A successful start increments the active count;
competing queue order and board task races are outside its bound.

`BoardFloorLiveness.cfg` must restore the floor and start the queued agent
under alternating fresh warning and healthy samples.
`BoardFloorLegacyFloor.cfg` must break `FreshFloorDecision` before the old
healthy window completes. `BoardFloorLegacyNoStart.cfg` must violate
`QueueStarts` under that same alternation. `BoardFloorCeiling7.cfg` checks the
capped formula at a seven-agent ceiling. `BoardFloorGrowth.cfg` checks that
above-floor growth advances by one after a healthy window when all pending
memory and CPU fit. `BoardFloorSafety.cfg` checks the fixed policy with invalid
samples, critical pressure, recheck failures, write failures, and native start
failure enabled. `BoardFloorStrictRecheck.cfg`, `BoardFloorStrictWrite.cfg`,
`BoardFloorStrictStart.cfg`, and `BoardFloorStrictCriticalWrite.cfg` expose the
external failure limits. `BoardFloorCoverage.cfg` requires nonzero coverage for
every modeled transition.

The queue-start liveness result assumes each modeled good sample is fresh,
complete, noncritical, and within the initial board-read budget; the board
recheck succeeds; the setter writes and reads back the target; one eligible
queued job has a valid native identity and free task slot; and the external
scheduler eventually starts it. In `steady`, a healthy sample also abstracts
the source's other growth-safety vetoes as clear, while `growthFits`
represents the pending memory and CPU budget checks. These veto fields are not
explored independently. The model does not prove raw sensor parsing, active-ID
equality under all races, user-visible installation behavior, retries after a
failed native start, or permanent availability of the board service.

## Source synchronization

The MO-26 installation of `70bb996bc105` was rolled back after the original
overload replay encountered missing `cpu_busy_pct` and the board decision
raised `TypeError` before cutting the board limit. Production uses `89f73fe`
with the local heavy-wait pause-off hotfix. Check installation status before
using this record; local hotfix files need not match the source commit.
The BoardFloor TLC receipts under
`/Users/shyamsivakumar/.herdr-projects/reports/mac-ops/2/formal-proof/board-floor/`
still describe the prior `e778e78a5b86` snapshot until
`/maintain-formal-verification-skill` reruns them against the measured-budget
paths. `Governor.tla`'s board snapshot is historical; `BoardFloor.tla` owns
current board-floor claims. After later source changes, compare the named
functions and hashes, rerun the affected model, and move this sync commit only
after the verification again describes the code.

The installed release records `source_commit` in
`~/.local/state/mac-ops/installation.json`. Read it and check for local hotfix
metadata before identifying the running controller and supervisor.

`replay_controller.py --boardfloor` selects a controller row near Unix time
`1793150983.444375`. Controller logs rotate, so that row can be gone from every
live log; the replay then fails with "No valid board-floor source row matched".
Use the recorded deadlock row instead when it is still present: replay it
through `_board_control_tick` with the board command mocked and compare the
target and the board write between the previous release and the current one.
