# Heavy workload state chart

## Admission

```mermaid
stateDiagram-v2
    [*] --> Queued
    Queued --> Waiting: telemetry or capacity unavailable
    Waiting --> Queued: fresh sample
    Queued --> Starting: fresh capacity, queue head, free slot, locked reservation
    Queued --> Waiting: legacy marker or slot limit reached
    Waiting --> Cancelled: interrupt or wait timeout
    Starting --> Running: launch verified process group and watchdog
    Starting --> Failed: launch or identity check fails
```

Review jobs sort ahead of ordinary queued jobs. Each queue entry stores the waiting process identity and is removed when that process exits or changes identity. Reservation and queue removal use the same registry lock. A new job cannot start while `legacy-registry.json` exists.

The first queued reviewer gets the next available admission. Existing workloads are not preempted to serve a reviewer.

The slot limit is the minimum of fresh controller `heavy_slots`, physical CPU cores, and whole 6 GiB units of physical memory. The controller contract must have an integer `heavy_slots`, a current Unix `updated_at`, and the current kernel `boot_id`. Missing, malformed, stale, or cross-boot capacity holds admission. The project lock is acquired after the global reservation, and the supervisor refreshes the registry heartbeat while waiting for it.

## Running and pause recovery

```mermaid
stateDiagram-v2
    Running --> PauseRequested: pressure or missing telemetry for 15 seconds
    PauseRequested --> Paused: own process group identity verified, SIGSTOP succeeds
    PauseRequested --> PauseRequested: verification or signal fails, retry
    Paused --> Running: 10 healthy seconds, free active slot, positive fresh capacity, verified SIGCONT
    Paused --> Paused: capacity is zero or verification or signal fails, retry
    Running --> Terminating: user interrupt, explicit curtail, or watchdog failure
    PauseRequested --> Terminating: user interrupt, explicit curtail, or watchdog failure
    Paused --> Terminating: user interrupt, explicit curtail, or watchdog failure
    Terminating --> Complete: verified group exits and registry cleanup finishes
```

Only the registered workload's own isolated process group receives pause, resume, or termination signals. The supervisor stays outside that group and keeps the watchdog heartbeat current while the workload is paused. Host pressure and missing telemetry never trigger termination. Capacity zero blocks admission and resume, and capacity zero alone does not trigger a pause. Paused jobs remain in admission accounting. A resume also waits until the verified count of active nonpaused jobs is below the fresh slot limit.

While pressure continues, the registry permits one new pause request every 5 seconds. An unconfirmed request blocks duplicates until its owner retries. A paused ordinary job does not block selection of another running ordinary job, and reviewers are selected only after no ordinary workload remains running.

Ordinary direct `xcodebuild` commands keep the shared DerivedData rewrite and run through `/usr/sbin/taskpolicy -b`. Review commands keep the same project protections but do not receive background scheduling.
