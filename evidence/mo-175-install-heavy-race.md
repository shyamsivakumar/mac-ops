# MO-175 RCA: post-merge install rolled back with `heavy_error: _HeavyCensusRace: heavy RSS process identity is unavailable`

Refs #111. Frozen base: `842a196` (`main`, identical to `origin/main`).

Read-only investigation. No installer, `emp-hub`, launchd job or runtime service was run or
restarted, and no configuration value is printed here. The only change in this branch is this
file. The census probes below read the process table, `ps` output and the heavy registry; they
write nothing outside this worktree's scratch directory.

## CAUSE

Two independent faults line up in the post-install observation window.

1. The heavy census compares **two** process listings that are tens of milliseconds apart, and
   the heavy workload's process group forks children continuously. A child forked between the
   two listings is missing from the first listing and present in the second, so the census
   raises `_HeavyCensusRace("heavy RSS process identity is unavailable")`
   (`board_resources.py:349-352`). The race is a property of a busy host, not of the install:
   it fired on 45 of the 6329 controller ticks recorded between `05:47:00` and `16:22:07`,
   including at `16:12:27.706630`, 63 seconds **after** the rollback, with no install running.
2. The post-install observation treats **any** `heavy_error` on **any** tick in the window as
   proof that the new runtime is broken (`scripts/install_if_behind.py:485-486`), and returns
   at the first such tick (`:687-694`). On this machine 5.5 % of ticks carry an error and a
   180 s window holds a median of 35 ticks, so **37 % of observation windows carry at least
   one error**. The tick that rolled this install back was produced by a controller running
   byte-identical code to the release it "rejected" (the release digest is the same
   `091e09889e8b254d2a47` at `6503cf0` and at `842a196`).

The census race is therefore a false alarm that the rollback guard cannot distinguish from a
broken install. The guard is what turns a 0.7 %-per-tick sampling race into a rolled-back
install.

## Evidence

### 1. The hub log

`~/.empryo-hub/hub.log:7806-7807`:

```
2026-11-11 16:10:47 merged shyamsivakumar/mac-ops#110 (merge) for emp:5a81921e-dabb-48ca-a40d-3fa78bb88fa6
2026-11-11 16:11:24 post-merge warning for shyamsivakumar/mac-ops: {'status': 'failed', 'configured': True, 'base': 'main', 'fastForward': {'status': 'ok', 'from': '6503cf0', 'to': '842a196'}, 'install': {'status': 'failed', 'decision': 'rolled_back', 'reason': 'heavy_error: _HeavyCensusRace: heavy RSS process identity is unavailable'}, 'configSync': [{'status': 'skipped', 'reason': 'install did not complete'}]}
```

The fast-forward succeeded, so the install ran against `842a196`; the rollback is the install
step's own decision (`empryo/bin/emp_post_merge.py:95` maps `rolled_back` to
`status: failed`), and the hub's `configSync` - the step that would have shipped MO-167,
MO-170 and MO-174 - was skipped because "install did not complete".

The same guard rolled back four earlier merges that day with a different reason
(`board_slots_dropped_to_zero_without_veto`, `hub.log:6681`, `:6713`, `:6943`, `:7046`);
MO-173 fixed that one (`e863cce`), and this ticket is the next false guard in the same family.

### 2. The controller rows in the observation window

`~/.local/state/mac-ops/controller.jsonl`, rows written after the install started:

| tick | heavy_error | board_error | census.registry_active | heavy_decision.reason |
|---|---|---|---|---|
| `16:10:52.118606` | - | `RuntimeError: board admission snapshot timed out` | 1 | `baseline_floor_hold` |
| `16:11:05.224645` | - | - | 2 | `await_capacity_headroom` |
| `16:11:11.395115` | - | - | 2 | `await_capacity_headroom` |
| `16:11:21.040216` | `_HeavyCensusRace: heavy RSS process identity is unavailable` | - | (null) | (null) |
| `16:11:24.015365` | - | - | 2 | `compressor_baseline` |

The install wrote the release files at `16:10:57` (the `mtime` of all eight files in
`~/.local/lib/mac-ops/091e09889e8b254d2a47/`), so `install_started_at` is just before
`16:10:57` and the `16:10:52` row falls outside the window. The observation therefore saw
exactly three ticks and stopped at the third.

The controller was restarted by the install itself: `install.py:246` boots the
`com.shyam.load-backstop` agent out and `install.py:253-255` bootstraps it again, and
`~/.local/state/mac-ops/com.shyam.load-backstop.stdout.log` shows a `controller_start`
line immediately before the `16:11:05.224645` tick, i.e. the `16:11:05`, `16:11:11` and
`16:11:21` rows all come from the freshly started controller.

The rollback receipt follows one second later:
`~/.local/state/mac-ops/installation.json` has `installed_at: 1794442284.042367`
(`16:11:24.04`), `source_commit: 6503cf0` and `release: .../091e09889e8b254d2a47`.

### 3. The tick that tripped the guard ran the same bytes as the release it rejected

`install.py:52-58` names the release directory by the sha256 of the runtime file set
(`install.py:17-18`). Recomputing that digest at both commits:

| commit | release digest |
|---|---|
| `6503cf0` (pre-merge) | `091e09889e8b254d2a47` |
| `842a196` (post-merge) | `091e09889e8b254d2a47` |
| `b5b6ff3` (last clean install) | `091e09889e8b254d2a47` |

PR #110 changed no runtime file, so the controller that ticked during the observation was
executing byte-identical code to the release the observation was judging. The
`runtime` field of every row in the window is that same directory.

### 4. A heavy workload was churning exactly during the window

`~/.local/state/mac-ops/heavy-jobs/events.jsonl`:

```
2026-11-11T16:10:53 queued   | role review | cmd check.sh
2026-11-11T16:10:56 started  | job 24dfe14c7e66 | role review | cmd check.sh
2026-11-11T16:11:11 queued   | role review | cmd check.sh
2026-11-11T16:12:23 started  | job 87f51be8881d | role review | cmd check.sh
```

The Opus review gate for PR #110 was running as a heavy workload (`check.sh`) from
`16:10:56`, and the census rows show `census.registry_active = 2` at `16:11:11` and
at `16:11:30`. The tracked workload groups were therefore live and forking while the
observation ran.

### 5. The same error without any install

`controller.jsonl`, `2026-11-11T16:12:27.706630`:
`_HeavyCensusRace: heavy RSS process identity is unavailable`. The rollback had already
happened at `16:11:24`. The race is ambient.

## The code path that raises `_HeavyCensusRace`

```
board_governor.py:1247   census = board_resources.active_heavy_census()
board_governor.py:1262-1263   except Exception -> entry["heavy_error"] = type(exc).__name__ + ": " + str(exc)...
board_resources.py:432-438   active_heavy_census(): up to 3 attempts, immediately, no pause
board_resources.py:381   processes = heavy.process_table()          <- listing #1 (identity)
board_resources.py:422   job_rss_bytes = _active_group_rss(heavy, processes, active_workload_pgids)
board_resources.py:338   output = ps -axo pid=,pgid=,rss=,lstart=   <- listing #2 (RSS)
board_resources.py:349-352   info is None and pgid in pgids -> raise _HeavyCensusRace(
                                    "heavy RSS process identity is unavailable")
heavy.py:487-511   process_table(): ps -axo pid=,ppid=,pgid=,uid=,stat=,lstart= + libproc refinement
heavy.py:1956-1973   the workload is launched with start_new_session=True, so it owns its
                     process group and every child it forks inherits that pgid
scripts/install_if_behind.py:485-486   row["heavy_error"] -> fatal_errors
scripts/install_if_behind.py:687-694   observe_controller returns at the first fatal error
scripts/install_if_behind.py:1180-1224   observation failed -> rollback_to_release(...)
```

The census holds **two** listings that are not simultaneous. Listing #1 is taken by
`heavy.process_table()`; listing #2 is a separate `ps` call made afterwards. On this host
the gap is measurable: `heavy.process_table()` took 33-370 ms (mean 48 ms) over 377 probes,
because it lists ~1170 processes and then refines every own-uid pid through libproc
(`heavy.py:496-510`). Any child forked inside that gap appears in listing #2 with the
workload's pgid and is absent from listing #1.

## Why the census races: the probe

Two read-only probes were run against the live registry and workload. Both patched
`board_resources._active_group_rss` (so the tracked pgids and the identity table are the
real ones), recorded the pid set of listing #1 (`heavy._parse_process_table`), recorded the
pids that `heavy._native_process_info` dropped, and classified the offending pid.

Probe 1, 872 census attempts in 240 s: **199 races (22.8 % per attempt)**. Every single
offending pid had `in_t1_ps = false` and `dropped_by_libproc_none = false`: the process was
**never in listing #1**. Among the sampled races were one `heavy workload RSS is unavailable`
and one `heavy RSS process census is incomplete` (a member that vanished).

Probe 2, 377 attempts in 200 s: **70 races (18.6 % per attempt)**, and the group members at
the moment of the race were captured:

```
pid 79345  pgid 79345  Ss   bash scripts/check.sh --full          <- the heavy workload
pid 81165  pgid 79345  S    bash scripts/check.sh --full
pid 81167  pgid 79345  S    node test_srw16_release_gate.js --jobs 2
pid 81381  pgid 79345  S    node scripts/srw_trader_boot_eval.cjs --sha ba8baac2...
pid 82913  pgid 79345  S    docker exec -e NODE_OPTIONS= srw713-shadow-8e0c6b7cb839 node -e ...
pid 82908  pgid 79345       <- the offending pid: forked inside the gap, absent from listing #1
```

The workload group's membership churns at 0.615 new processes per second across the tracked
groups; 61 of 376 half-second samples caught a new member. With a ~48 ms gap and that churn
rate, a fork lands inside the gap roughly one attempt in five - which is the 18.6-22.8 %
measured.

The controller's own numbers agree. 45 of the 6329 recorded ticks (0.71 %) carry the census
race; the census retries three times inside one tick with no pause, so the three attempts
share the same churn window, and `0.19^3 = 0.0069` matches the observed 0.71 % per tick.

## Hypotheses and the tests that told them apart

| # | Hypothesis | Test | Result |
|---|---|---|---|
| H1 | The install caused the race: its restart of the controller, or one of its own processes, disturbed the census | (a) The offending pids are children of the heavy workload group (probe 2: pid 82908 with pgid 79345, whose leader is `bash scripts/check.sh --full`), never an installer or controller process; (b) the workload runs in its own session (`heavy.py:1970` `start_new_session=True`), so only its descendants can hold its pgid; (c) the same error recurs at `16:12:27.706630`, after the rollback, with nothing running; (d) 45 race ticks over the recorded day against 5 installs; (e) the install writes eight files and re-bootstraps one launchd agent - it never touches the heavy registry, a workload or a workload pgid | Rejected. The install did not cause the race; it only restarted the controller, which then ticked inside the observation window |
| H2 | The identity was lost because a process **exited** between the two listings (a dropped pid, or a zombie still listed by `ps`) | Probe instrumentation recorded, for every race, whether the offending pid was in listing #1's pid set and whether `heavy._native_process_info` had dropped it. Every offending pid was `in_t1_ps = false` and `dropped_by_libproc_none = false`: it was never in listing #1. The opposite branch (a member that vanished between the listings) fired once in the probe's 872 attempts and 0 times in the 6329 recorded ticks | Rejected. The race is a **fork**, not an exit |
| H3 | The identity check mis-compares the two start tokens (`ps` `lstart` has second resolution, libproc has microseconds) | The comparison at `board_resources.py:357` truncates both sides to whole seconds (`int(info.start_epoch) != int(ps_epoch)`), so equal starts compare equal; and a mismatch would raise "heavy RSS process identity **changed during sampling**", a message that appears 0 times in 6329 ticks, while the observed message is the "unavailable" one raised at `:351` | Rejected. The observed branch is a missing identity, not a changed one |
| H4 | The `ps` listing was truncated or the workload group was mis-read | The same listing that produced the offending pid also contained the rest of the group (probe 2 lists 15 live members of pgid 79345 in one snapshot), and the offending pid had a live parent inside the group (pid 83106, ppid 76937, `(docker)`) | Rejected |
| H5 | The guard correctly identified a broken runtime | (a) The release digest is identical at `6503cf0` and `842a196`, so the ticking controller ran the same bytes as the release it was judging; (b) the governor treats the census failure as a soft failure - it publishes a conservative capacity and keeps ticking (`board_governor.py:1262-1284`); (c) the very next tick (`16:11:24.015365`) is clean; (d) the census race is 0.71 % of ticks and every other error class on this host is equally ambient | Rejected. The tick was a false alarm, and the guard had no way to know that |

## The guard's error floor

Every controller error on `2026-11-11 05:47:00` - `16:22:07` (`controller.jsonl` +
`controller.previous.jsonl`, 6329 ticks, 348 error ticks = 5.5 %):

| ticks | field | message |
|---|---|---|
| 201 | `board_error` | `RuntimeError: board admission snapshot timed out` |
| 46 | `heavy_error` | `TelemetryError: host telemetry sample was stale on arrival` |
| 45 | `heavy_error` | `_HeavyCensusRace: heavy RSS process identity is unavailable` |
| 26 | `heavy_error` | `TelemetryError: host telemetry sample was incomplete` |
| 22 | `heavy_error` | `TelemetryError: native telemetry command failed` |
| 4 | `heavy_error` | `RuntimeError: heavy RSS snapshot timed out` |
| 3 | `heavy_error` | `_HeavyCensusRace: heavy workload RSS is unavailable` |
| 1 | `board_error` | `TimeoutExpired: herdr-projects set board.agents 0 timed out after 4 seconds` |

Sliding a 180 s window over every tick (6329 windows, median 35 ticks per window), the share
of windows that contain at least one error of a given class:

| class | share of windows |
|---|---|
| telemetry sampling failure | 30.2 % |
| host command timeout (`board_error`, `heavy RSS snapshot timed out`) | 18.7 % |
| heavy census race | 15.4 % |
| **any error (what the guard treats as a rollback)** | **37.4 %** |
| no error at all | 62.6 % |

The observation demands a *perfect* window and returns at the *first* error, so on this host
roughly **two installs in five are rolled back for host noise**, whatever the install did.
Counting rules do not separate the noise from a real regression: 29.9 % of windows hold two
or more error ticks, 20.3 % repeat the same error message, and every error this host
produces is a sampling failure - not one of the 348 error ticks says the runtime is broken.

## Smallest fix

In `scripts/install_if_behind.py`, function `evaluate_controller_ticks()` (`:403-542`):
**a heavy error that names a host reading which did not arrive is churn, not proof that the
install broke the runtime - unless the controller reports it on every tick of the window.**

```python
TRANSIENT_HEAVY_ERRORS = ("_HeavyCensusRace:", "TelemetryError:")


def transient_heavy_error(err):
    """True for a heavy error that is a failed host reading, not a broken runtime."""
    return isinstance(err, str) and err.startswith(TRANSIENT_HEAVY_ERRORS)
```

and in the per-row loop, replacing `:485-486`:

```python
        heavy_error = row.get("heavy_error")
        if heavy_error:
            if transient_heavy_error(heavy_error):
                census_churn.append(f"heavy_error: {heavy_error}")
            else:
                fatal_errors.append(f"heavy_error: {heavy_error}")
```

and after the loop, to keep the rule's teeth for an install that breaks the census for good:

```python
    if (
        min_ticks
        and len(matching) >= min_ticks
        and all(row.get("heavy_error") for row in matching)
    ):
        fatal_errors.append("heavy_error on every observed tick")
```

Why this is the smallest sufficient change:

- It reuses the bucket the file already has for exactly this purpose. `census_churn`
  (`:433`) already carries the board agent census churn (`CENSUS_PROCESS_EXIT`, `:392-400`)
  and `docs/state-charts/installation.md:16` records the same rule for that case: "Observing
  --> Observing: agent process exits during the census". A heavy workload forking a child
  during the census is the same kind of event.
- It keeps the guard's teeth. A census or telemetry failure on **every** tick of the window
  is still fatal, so an install that really breaks `board_resources.py` or `heavy.py` is
  still rolled back. The controller dying is still fatal through the untouched
  `insufficient_controller_ticks` and `controller_status_stale_at_end` rules.
- It leaves every other error fatal: `board_error`, `capacity_error`,
  `critical_curtailment_error`, `board_restart_error`, and any heavy error that is not a
  failed host reading (`heavy registry records are unavailable or corrupt`, `kernel boot
  identity is invalid`, ...).
- It does not weaken any existing test. `tests/test_install_if_behind.py:170-196`
  (`test_controller_failure_stops_observation_for_rollback`) pins a `board_error` as fatal
  and is untouched; the churn test at `:70-81` still passes. A new test is needed for the
  transient heavy error and for the every-tick rule.
- It would have kept this install. The three ticks in the window were clean, clean, raced;
  the next twelve ticks (`16:11:24.015365` .. `16:12:20.533846`) are clean, and the
  `16:12:27.706630` race would itself be churn. The observation would have passed, the
  release `842a196` would have stayed installed, and `configSync` would have shipped
  MO-167, MO-170 and MO-174.

The same diff with `"RuntimeError: heavy RSS snapshot timed out"` added to
`TRANSIENT_HEAVY_ERRORS` covers the remaining 4 heavy ticks. It is left out of the smallest
change because it is not the reported symptom.

### The upstream alternative (not required)

The false error can also be removed at its source, in `board_resources._active_group_rss`
(`:349-352`): a pid that appears in listing #2 with a tracked pgid but not in listing #1 is
a **new child of the workload** (only descendants can hold that pgid, because the workload
owns its session), so it could be counted instead of raising. That removes the error for the
governor as well, and the governor would stop dropping to a conservative capacity on 0.7 % of
ticks. It is not proposed as the primary fix because it changes an identity check in the
admission path, and because on its own it leaves the telemetry and timeout classes rolling
installs back.

### Residual risk the owner has to decide

After the change above, the `board_error` class still rolls installs back: 201 of the 348
error ticks are `RuntimeError: board admission snapshot timed out`, and 27.6 % of 180 s
windows contain one. That class is pinned by an existing test
(`tests/test_install_if_behind.py:170-196` expects a `board_error` to stop the observation
and roll the install back), so changing it needs the owner's approval of that exact edit. It
is the next false guard in the same family and it is the largest remaining one.

## Sources

- `~/.empryo-hub/hub.log:7806-7807` (merge and post-merge warning), `:6681`, `:6713`,
  `:6943`, `:7046` (earlier rollbacks).
- `~/.local/state/mac-ops/controller.jsonl` (rows `16:10:52.118606` .. `16:12:35.547859`,
  the error census over the 6329 ticks recorded from `05:47:00` to `16:22:07`, the 180 s
  window sweep).
- `~/.local/state/mac-ops/com.shyam.load-backstop.stdout.log` (`controller_start` lines that
  date the controller restarts at `16:11:05` and `16:11:30`).
- `~/.local/state/mac-ops/heavy-jobs/events.jsonl` (the review workload `24dfe14c7e66`
  started `16:10:56`).
- `~/.local/state/mac-ops/installation.json` (rollback receipt: `installed_at`
  `1794442284.042367` = `16:11:24.04`, `source_commit` `6503cf0`, release
  `091e09889e8b254d2a47`).
- `scripts/install_if_behind.py:392-400` (churn rule), `:403-542` (the guard), `:664-702`
  (observation loop), `:838-1239` (install, observe, rollback).
- `board_resources.py:335-369` (`_active_group_rss`, the raise at `:351`), `:372-429`
  (`_active_heavy_census`), `:432-438` (the three attempts).
- `board_governor.py:1230-1290` (`controller_tick`, `heavy_error` at `:1263`),
  `:1424-1446` (the controller loop).
- `heavy.py:487-511` (`process_table`), `:1119-1165` (`legacy_slot_count`),
  `:1221-1234` (`_record_live`), `:1956-1973` (workload launch, own session).
- `install.py:17-18`, `:52-58` (release digest), `:224-225` (release write), `:246`, `:253-255`
  (agent restart).
- `empryo/bin/emp_post_merge.py:88-97` (install decision mapping, `rolled_back` at `:95`).
- `docs/state-charts/installation.md:16-19`, `:36-43` (documented intent).
- `tests/test_install_if_behind.py:70-81` (churn), `:170-196` (board error is fatal),
  `:198-271` (the zero-slot rules).
- Probes (read-only, in this worktree's scratch directory):
  `.empryo/tmp/tabs/00740b4a-8a19-4b90-b828-5306b28e4e60/probe_census.py` and
  `probe_churn.py`. Both patch `board_resources._active_group_rss`,
  `heavy._parse_process_table`, `heavy._native_process_info` and `heavy.process_table` to
  record the two listings' pid sets, the pids libproc dropped, the elapsed time of
  `process_table()` and the members of the tracked workload groups, then call the real
  `board_resources.active_heavy_census()`. Nothing is written outside the scratch directory.

## Uncertainty

- `install_started_at` is not logged. It lies between the fast-forward (`16:10:47`) and
  the release write (`16:10:57`); the `16:10:52` row would have been inside the window if
  the stamp were earlier, and it carries a `board_error` - the rollback reason in the log is
  the heavy error, so the stamp must be after `16:10:52.118606`.
- The tick's own `updated_at` is the row's wall clock, written after the tick finished
  (`board_governor.py:1252`); the census itself ran a few tens of milliseconds earlier.
- The probe rates (18.6 % and 22.8 % per attempt) were measured on the live host with two
  heavy workloads running, minutes after the incident. The per-tick rate that the controller
  recorded that day (0.71 %) is the authoritative one and is consistent with them
  (`0.19^3`).
- The proposal is derived from the recorded evidence only. It has not been applied or
  exercised here: this ticket is read-only, and proving it against the live installer would
  have required running the installer, which the ticket forbids.
- Whether the `board_error` class should also become churn is a policy decision the owner
  has to make; it changes the meaning of an existing test.
