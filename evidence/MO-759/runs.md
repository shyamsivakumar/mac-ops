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
