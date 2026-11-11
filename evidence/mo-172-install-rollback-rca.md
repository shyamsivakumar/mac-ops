# MO-172 RCA: post-merge install rolled back with `board_slots_dropped_to_zero_without_veto`

Refs #104. Frozen base: `7bd870c8672d414090ff188abdf9ea57c014d950` (`main`, identical to
`origin/main`).

Read-only investigation. No installer, `emp-hub`, launchd job or runtime service was run or
restarted, and no configuration value is printed here. The only change in this branch is this
file.

## CAUSE

The post-install observation in `scripts/install_if_behind.py` fails an install when any
controller tick in the observation window reports `board.decision.target == 0` with no
`host_veto` (`scripts/install_if_behind.py:460`, reason emitted at `:517`), but the board
governor parks the board at zero slots on purpose while it waits for a healthy window
(`board_governor.py:1087-1103`, reason `await_healthy_window`, `floor_raise_fits: false`),
and on this machine the board was already at zero slots before the install started, so a
healthy install was rolled back on a pre-existing, self-explained zero-slot state.

Supporting evidence, in order:

1. The hub log, `~/.empryo-hub/hub.log:6943` (merge at `:6942`):

   ```
   2026-11-11 10:19:34 merged shyamsivakumar/mac-ops#102 (merge) for emp:63c47452-f3bc-450e-97c1-54c840bb8deb
   2026-11-11 10:19:50 post-merge warning for shyamsivakumar/mac-ops: {'status': 'failed', 'configured': True, 'base': 'main', 'fastForward': {'status': 'ok', 'from': '6b1b46e', 'to': '7bd870c'}, 'install': {'status': 'failed', 'decision': 'rolled_back', 'reason': 'board_slots_dropped_to_zero_without_veto'}, 'configSync': [{'status': 'skipped', 'reason': 'install did not complete'}]}
   ```

   The fast-forward succeeded, so the install ran against `7bd870c` and the rollback is the
   install step's own decision, not a merge failure. `empryo/bin/emp_post_merge.py:95` maps
   that decision to `status: failed`.

2. The guard, `scripts/install_if_behind.py:452-469` and `:516-517`:

   ```python
   current = board_block.get("current", board_dec.get("current"))
   ...
   host_veto = board_dec.get("host_veto")
   reason = board_dec.get("reason")
   ...
   if target == 0 and host_veto is None:
       unexplained_zero_board_slots.append({...})
   ...
   if unexplained_zero_board_slots:
       reasons.append("board_slots_dropped_to_zero_without_veto")
   ```

   The rule reads two numbers only: the board's target slot count and whether a host veto
   was reported. It ignores the board's own current level, the governor's `reason`, and
   whether the board had any live slots at all before the install.

3. The governor, `board_governor.py:1087-1103`: with no host blocker and a floor that does
   not fit in the memory headroom (`floor_raise_fits: false`, `:1052-1061`), the governor
   keeps `target = current` (`:1062`) and, until its 60 s growth hold elapses, records
   `reason = "await_healthy_window"` with **no** `host_veto`. `host_veto` is reserved for
   host-level blockers (`:943` `host_sample_unavailable`, `:954` admission block, `:970-972`
   `compressor_growth`), so a routine hold is veto-free by design.

4. The controller rows, `~/.local/state/mac-ops/controller.jsonl`, show the board at zero
   slots before and after the install (see the table below). The pre-install row is
   `10:19:32.383`; the install wrote the release files at `10:19:39`, so the board was
   already empty when the install started.

## What the guard measures

`evaluate_controller_ticks()` (`scripts/install_if_behind.py:403-539`) reads
`controller.previous.jsonl` and `controller.jsonl` from the state dir
(`:542-561`), keeps the rows written at or after `install_started_at` whose `runtime`
matches the installed release (`:418-427`), and from each row's `board.decision` it
measures:

- `board_decisions`, `heavy_decisions` - were the board and heavy tiers still deciding?
- `fatal_errors` - `board_error`, `capacity_error`, `critical_curtailment_error`,
  `board_restart_error`, `heavy_error`, census errors, pause errors (`:473-505`).
- `unexplained_zero_board_slots` - rows with `decision.target == 0` and `decision.host_veto`
  is `None` (`:460`).
- `min_board_target`, `min_board_current` - the lowest values seen (`:537-538`).

`observe_controller()` (`:661-699`) polls every 5 s up to 180 s, and returns the summary
immediately when `unexplained_zero_board_slots` is non-empty (`:684-691`), so a single
zero-slot tick is enough to fail the install. On failure `run_install_if_behind()` rolls
back to the previous receipt and returns `decision: "rolled_back"` with the joined reasons
(`:1177-1221`).

The rule's documented intent is `docs/state-charts/installation.md:18` and `:39-40`:
"Observing --> RolledBack: controller error or slots hit 0 without a veto".

## Before and after numbers

Board and heavy tiers per controller tick around the install (`controller.jsonl`):

| tick | board current | board target | board active | host_veto | reason | floor_ready / raise_fits | heavy slots |
|---|---|---|---|---|---|---|---|
| `10:19:32.383` (before the install) | 0 | 0 | 0 | `null` | `await_healthy_window` | true / false | 3 |
| `10:19:37.528` | 0 | 0 | 0 | `null` | `await_healthy_window` | true / false | 3 |
| `10:19:41.963` | 0 | 0 | 0 | `first swap sample; normal wait, a few seconds` | same | false / false | 2 |
| `10:19:47.143` | 0 | 0 | 0 | `null` | `await_healthy_window` | true / false | 2 |
| `10:19:52.573` | 0 | 0 | 0 | `first swap sample; normal wait, a few seconds` | same | false / false | 2 |

All five ticks carry the same `runtime`, `~/.local/lib/mac-ops/091e09889e8b254d2a47` - the
release directory the ticking process ran from, which is also the directory the install
wrote into.

Before: board current 0, target 0. After: board current 0, target 0. The board did not
change across the install - the guard's own `min_board_target` and `min_board_current`
(0 and 0) are the same numbers the board had before the install. Heavy capacity was
healthy throughout (2-3 slots); only the board tier was parked.

Why the board sits at zero: memory headroom was ~7.8 GB against an agent memory budget of
2 GiB and a floor of 6 agents, so `floor_raise_fits` was false and the governor waited out
its growth hold instead of admitting agents. Swap and compressor pressure kept resetting
that hold, which is why the ticks alternate between veto-free `await_healthy_window` rows
and veto rows.

The same reason rolled back two earlier merges the same day, each right after a
veto-free zero-slot tick, and one merge deferred instead (a deferral is not a failure:
`emp_post_merge.py:93-94` maps exit 75 to `status: deferred`):

| merge | hub log | outcome | last veto-free zero-slot tick before it |
|---|---|---|---|
| PR #95 (`e5e78a3` -> `b852960`) | `hub.log:6681`, 09:22:35 | `rolled_back`, same reason | `09:22:32.739` |
| PR #98 (`b852960` -> `37d10da`) | `hub.log:6713`, 09:33:46 | `rolled_back`, same reason | `09:33:43.779` |
| PR #100 (`37d10da` -> `6b1b46e`) | `~/.empryo-hub/merges.jsonl`, 09:42:32 | install deferred, post-merge status `ok`: `board_host_veto=memory-pressure-warning-low-free, heavy_host_veto=memory-pressure-warning-low-free` | veto was present |
| PR #102 (`6b1b46e` -> `7bd870c`) | `hub.log:6943`, 10:19:50 | `rolled_back`, same reason | `10:19:37.528` / `10:19:47.143` |

Over the whole day up to the rollback (`controller.jsonl`, 05:47:00 - 10:19:47), 2889 board
decisions were recorded: 1094 with target 0 and no veto (1037 of them `await_healthy_window`,
35 `one_agent_capacity_unavailable`, 22 `warning_pressure_hold`), 435 with target 0 and a
veto, and 1360 with target above 0. About 38 % of those ticks would trip this rule, so
any install on this machine had a high chance of being rolled back while the board was
parked at zero.

The asymmetry that matters: the pre-install gate in the same script
(`check_gate()`, `scripts/install_if_behind.py:266-389`) has no board-target rule at all. It
fails or defers only on a host veto, a stale controller status, or a heavy queue above 3
(`:361-364`). At 10:19:34 the same board state passed the gate cleanly, and the observation
failed sixteen seconds later.

## Hypotheses and the tests that told them apart

| # | Hypothesis | Test | Result |
|---|---|---|---|
| H1 | Stale repo routing: the hub installed from an old or wrong checkout, so the install and the observation disagree | (a) `hub.log:6943` shows `fastForward` ok `6b1b46e` -> `7bd870c`; (b) the live checkout is at that commit: `git -C ~/Code/mac-ops rev-parse HEAD` -> `7bd870c...`, branch `main`, origin `shyamsivakumar/mac-ops`; (c) `emp_post_merge.py:225-235` resolves the checkout from `~/.empryo/post-merge.json` ("mac-ops" -> `~/Code/mac-ops`) and refuses it unless the origin remote matches the merged repo; (d) `install_if_behind.py:1140-1143` raises "Post-install receipt source_commit does not match target origin/main" if the installed source is not the target commit - the recorded reason is the board reason, so the receipt matched `7bd870c`; (e) `~/.empryo-hub/routing.json` holds only model routing (per-type model names and turn limits) and no checkout path, so it cannot route an install to a stale tree | Rejected. The install ran against `7bd870c` from the live checkout; nothing was stale |
| H2 | An intended veto is missing: the governor should have set `host_veto` when it dropped the board to zero, and the zero should have been explained by a veto instead of by `reason` | Read the governor's decision path (`board_governor.py:1046-1105`): `host_veto` is set only by host-level blockers (`:943`, `:954`, `:970-972`), while the routine hold path sets `reason` and leaves `host_veto` `None`; then check the veto channel was alive in the same window: `10:19:41.963` and `10:19:52.573` carry `host_veto: "first swap sample; normal wait, a few seconds"` and other rows carry `compressor_growth` | Rejected. No veto was missing. The veto channel reported normally; the veto-free rows are the governor's ordinary healthy-window wait, and their own `reason` plus `floor_raise_fits: false` explain the zero |
| H3 | Counting bug: the guard counts a zero-slot tick it should not count | (a) The rule is `target == 0 and host_veto is None` (`install_if_behind.py:460`) and ignores `decision.reason`, `floor_ready`, `floor_raise_fits` and the board's `current` level, so the governor's deliberate hold is counted as an unexplained collapse; (b) the guard has no pre-install baseline - `evaluate_controller_ticks` only looks at rows at or after `install_started_at` (`:418`), so "the board was already at zero" is indistinguishable from "the board collapsed"; (c) the pre-install gate in the same file accepts the identical state (`:266-389`), so one fact is a pass at 10:19:34 and a failure at 10:19:50; (d) the day's census (2889 ticks, 1094 veto-free zero-slot ticks, 38 %) shows how often the rule fires on explained holds; (e) the release directory name is a digest of the runtime file set (`install.py:52-57`, `FILES` at `install.py:17-18`), and that digest is `091e09889e8b254d2a47` at `b5b6ff3`, `e5e78a3`, `b852960`, `37d10da`, `6b1b46e` and `7bd870c`, so the runtime filter at `:419-427` cannot tell a pre-install controller from a post-install one for this merge - the observation window is filled with ticks from the controller that was already running | Confirmed as the proximate cause. The guard counts the governor's explained, pre-existing hold as an unexplained collapse |
| H4 | Install ordering: the observation was made against the pre-install process, or the install ran in the wrong order relative to the controller | (a) `install_started_at` is stamped before the install runs (`install_if_behind.py:1108`, install at `:1126-1138`), and the release files were written at `10:19:39`, so the `10:19:37.528` tick was emitted while the install was still writing; (b) but the runtime digest is identical across the merge, so the running controller is executing byte-identical code to what was installed; (c) the zero-slot state existed before the install started (`10:19:32.383`, before `install_started_at`), so no ordering of install and observation explains the zero; (d) the rollback receipt was written at `10:19:50.03` (`~/.local/state/mac-ops/installation.json`, `installed_at: 1794421190.028`) with the previous release and commit `b5b6ff3`, i.e. the rollback restored the last release that installed cleanly | Partly true, not the cause. The observation can be satisfied by pre-install ticks (a), which weakens the runtime filter, but the board was already at zero (c) and the code was identical (b) |

## Smallest fix

One condition, in `scripts/install_if_behind.py`, in `evaluate_controller_ticks()` at line
460: count a zero-slot tick as unexplained only when the board actually dropped, i.e. when
it had live slots:

```python
if target == 0 and host_veto is None and current:
```

`current` is already computed at line 452 (`board_block.get("current", board_dec.get("current"))`).

Why this is the smallest sufficient change:

- It keeps the rule's teeth for the case it was written for. The existing test
  (`tests/test_install_if_behind.py:198-216`) builds a tick with `board.current = 14`,
  `target = 0` and no veto - a board that stopped admitting agents while agents were alive
  - and still expects the failure. That test is unchanged and still passes.
- It stops the false positive. Today's tick has `board.current = 0`: the board was already
  empty before the install, so nothing dropped, and the governor explained the hold in
  `reason` and `floor_raise_fits`.
- It does not blind the guard to a real collapse. If the install broke the board runner,
  the governor records `board_error` / `board_restart_error`, which the same function
  already treats as fatal (`install_if_behind.py:473-480`).

The stronger variant, if the owner wants the guard to compare against the pre-install
level instead: `check_gate()` already returns the pre-install `board_current` and
`board_target` from `controller-status.json` (`:354-357`), and `run_install_if_behind`
already computes `same_runtime_digest` (`:930`), so the observation could take the
pre-install board level as a baseline and defer (exit 75) rather than roll back when the
board was already at zero before the install. That is a larger change with a behavioural
decision attached (roll back vs defer), so it is not the smallest fix.

The file the fix lands in: `scripts/install_if_behind.py`, function
`evaluate_controller_ticks()`, line 460. Its test lives in
`tests/test_install_if_behind.py` (`test_zero_slots_still_fail_immediately`).

## Sources

- `~/.empryo-hub/hub.log` lines 6680-6681, 6712-6713, 6942-6943 (merges and post-merge
  warnings) and `~/.empryo-hub/merges.jsonl` (PR #95, #98, #100, #102 records, including
  the PR #100 deferral).
- `~/.local/state/mac-ops/controller.jsonl` (rows `09:22:27.642` .. `10:19:52.573` and the
  05:47:00 - 10:19:47 census).
- `~/.local/state/mac-ops/installation.json` (rollback receipt: release
  `~/.local/lib/mac-ops/091e09889e8b254d2a47`, `source_commit` `b5b6ff3`, `installed_at`
  `1794421190.028` = 10:19:50.03) and `~/.local/state/mac-ops/empryo-installation.json`.
- `scripts/install_if_behind.py:403-539` (the guard), `:661-699` (observation loop),
  `:266-389` (pre-install gate), `:930`, `:1108`, `:1126-1157`, `:1177-1221` (install and
  rollback).
- `board_governor.py:1046-1105` (board decision), `:943`, `:954`, `:970-972` (veto
  sources), `:761`, `:1234` (row fields).
- `install.py:17-18` (`FILES`), `:52-57` (release digest), `:224-250` (release write and
  receipt), `:276-312` (release validation and rollback).
- `empryo/bin/emp_post_merge.py:74-95` (install decision mapping), `:225-255` (checkout
  resolution and fast-forward).
- `docs/state-charts/installation.md:13`, `:18`, `:31-41` (documented intent).
- `tests/test_install_if_behind.py:18-34`, `:198-216` (the zero-slot rule's test).
- `git -C ~/Code/mac-ops cat-file --batch` digests of the runtime file set at `b5b6ff3`,
  `e5e78a3`, `b852960`, `37d10da`, `6b1b46e`, `7bd870c` (all `091e09889e8b254d2a47`).

## Uncertainty

- `install_started_at` is not logged. It lies between the merge at 10:19:34 and the
  release write at 10:19:39, so it cannot be said from the logs whether the trip came from
  the `10:19:37.528` tick or the `10:19:47.143` tick. Both are veto-free zero-slot rows
  with `current = 0` and `reason = await_healthy_window`, both are pre-existing holds, and
  the cause does not depend on which one tripped it.
- The install's own JSON result (the observation summary: `tick_count`, `span_seconds`,
  `min_board_target`, `min_board_current`) was captured by `emp_post_merge`'s subprocess
  and discarded; the hub kept only `decision` and `reason`. The numbers above are
  reconstructed from `controller.jsonl`, not read from the run.
- The observation window's exact bounds are not recoverable: `observe_seconds` defaults to
  180 s and `min_ticks` to 12 (`:670`), but the guard returns at the first unexplained
  zero-slot tick (`:684-691`).
- The last clean runtime install on this machine is `b5b6ff3` (PR #78). Every merge since
  (PR #95, #98, #100, #102) either deferred or rolled back, so the live runtime files are
  from `b5b6ff3`. Because none of those merges touched the runtime file set, the release
  digest - and therefore the runtime path the guard filters on - is unchanged across all
  of them.
- The one-line fix is proposed from the recorded evidence only. It has not been applied or
  exercised here: this ticket is read-only, and proving it against the live installer would
  have required running the installer, which the ticket forbids.
