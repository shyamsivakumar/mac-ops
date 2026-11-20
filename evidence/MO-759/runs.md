# MO-759 proof runs

Proof command (adapted: `coordinator/bin` is put on the path from the checkout or from a copy of origin/main).

## Before (origin/main copy of tick_health.py)

    AttributeError: module 'tick_health' has no attribute 'job_exit_alarms'

## After (branch)

    ALARM: job com.shyam.qabot-scout last exit 1

No line for the exit 0 and exit 78 jobs.

## Drift alarm (temp HOME, receipt pointing at the branch checkout, no live tick)

    first sight:  '' (marker install-drift.first-seen written)
    marker aged 31 minutes: ALARM: installed coordinator differs from <checkout> for 31 minutes: answer_format.py, ...

## Alarm routing

`tick_alarm()` returns text. Its three callers (`coordq status`, `overnight` report, `coord-tick`) print it. It does not call `alarms.py`, so these alarms reach no board file; they appear in the tick log, `coordq status` and the morning report.

## Suite timing, `python3 -m unittest tests.test_coordq_capacity` (the module that reaches `tick_alarm` via `coordq status`; not under heavy)

| Tree | Result |
| --- | --- |
| origin/main | 20 tests in 0.464s, 0.55s wall |
| branch before the fix | 20 tests in 2.958s, 3.04s wall (about 6x slower) |
| branch with the isolation skip | 20 tests in 0.456s, 0.52s wall |

The two external calls cost about 2.5s per `coordq status` run. Under `COORDINATOR_TEST_ISOLATION_DIR` (gh_isolation.ROOT_VAR) `tick_alarm()` now returns only the stale-log alarm and skips `launchctl list` and the installer status.
