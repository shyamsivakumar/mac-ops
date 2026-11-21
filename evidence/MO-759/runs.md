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

## Suite timing, `python3 -m unittest tests.test_coordq_capacity` (reaches `tick_alarm` through `coordq status`; run directly, not under heavy)

| Tree | Result |
| --- | --- |
| origin/main | 20 tests in 0.482s, 0.483s, 0.435s |
| branch, no cache (first version) | 20 tests in 2.958s |
| branch, drift status cached 10 minutes, no test-isolation branch | 20 tests in 0.514s, 0.509s, 0.529s (the first run after the cache was empty took 1.258s) |

`launchctl list` costs 0.04s, so it is not cached. `install_coordinator.py status` is cached for 10 minutes in `install-drift.status.json` next to `install-drift.first-seen`.

## Two back-to-back `coordq status` calls (temp HOME with a receipt, temp COORDQ_DIR and COORD_JOURNAL_DIR)

    run 1 (cache empty, real installer status): 1.174s
    run 2 (cache hit): 0.175s

## Nested smoke checks found by the full unittest run

`install_coordinator.py status` runs `coordq status` as a smoke check, and `coordq status` now runs the drift check, so the installer's own smoke check ran the installer's status inside it. `python3 -m unittest` on the branch took 443.9s with 13 errors in `tests.test_install_coordinator` (smoke `coordq status` timed out at 30s); origin/main ran 686 tests in 55.3s, OK.

Fix: the drift check runs `install_coordinator.py status --no-smoke` (new flag, status only, skips the smoke checks; `in_sync` and `differs` do not depend on them). After it:

    python3 -m unittest tests.test_install_coordinator tests.test_coordq_capacity: 80 tests in 12.9s, OK
    tests.test_coordq_capacity alone: 20 tests in 0.24s to 0.29s (cache hit)
    coordq status twice (temp HOME with receipt): 0.758s then 0.198s
