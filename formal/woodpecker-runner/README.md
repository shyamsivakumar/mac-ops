# Woodpecker runner lifecycle model

`RunnerLifecycle.tla` is an abstract model of the self-hosted Woodpecker runner on the M1. A job is registered, polled by a worker slot, run, reported, and the agent can be restarted or reinstalled while jobs are in flight. The model does not fix anything. It reproduces known problems as counterexamples.

## What is modelled

- Two worker slots on one native agent process (`WOODPECKER_MAX_WORKFLOWS=2` from MO-72) and two tasks.
- The server queue: pending tasks, a lease owner per running task, and the database state of each workflow.
- What really runs on the host, which differs from the server view after a restart or a partition.
- The install path: kickstart, a new release that may be broken, and an optional rollback step.
- A fault budget (`MaxFaults = 1`) so every run is finite. Restarts, installs and partition expiries each use one fault.

## Source facts

- Woodpecker v3.16.0 `server/queue/fifo.go`, `resubmitExpiredPipelines`: a running task whose lease passed goes back to the front of pending and another worker can poll it at once. A report for a task that is no longer running only removes it from pending. A resubmitted task whose persisted row is gone is dropped as stale, and the database row stays `running`.
- Woodpecker v3.16.0 `agent/runner.go`: the cancel of the first agent arrives only through its gRPC Wait stream, so a slow or partitioned agent keeps executing. Extend failures are only logged.
- `~/Code/woodpecker-ci/scripts/bootstrap.sh` on the M1 runs `set -eu`, `compose up -d --force-recreate` and `scripts/verify.sh`. It has no automatic rollback. The plist edit and `launchctl kickstart -k` are also manual, with a `.before-max2` copy.
- Incident: workflow 4254 (pipeline 1449) was running when the MO-72 reinstall restarted the agent at 2026-10-30T03:00:46Z. The server resubmitted it at 03:01:40Z, dropped it as stale at 03:10:45Z, and the row is still `running`.

## Configs and expected results

| Config | Settings | Checks | Expected |
| --- | --- | --- | --- |
| `RunnerNoPartition.cfg` | Partition off, StaleDrop off, Rollback on | NoDoubleRun, TypeOK, RunnerComesBack, FailedInstallRollsBack, JobsReported | Pass |
| `RunnerDoubleRun.cfg` | Partition on | NoDoubleRun | Fails. A lease expires while worker 1 still runs the task, and worker 2 polls it. |
| `RunnerInstallGap.cfg` | Partition off | RunnerAlwaysUp | Fails. Every install or restart takes the only native macOS agent down (both MO-72 slots share one process), so darwin jobs have no runner until it comes back. The real gap on 2026-10-30 was 11 seconds (agent.log 03:00:46Z shutdown, 03:00:57Z start). |
| `RunnerStaleDrop.cfg` | StaleDrop on | JobsReported | Fails. A restart orphans a lease, the task is resubmitted and dropped, and the database stays `running` (workflow 4254). |
| `RunnerNoRollback.cfg` | Rollback off | RunnerComesBack, FailedInstallRollsBack | Fails. A broken new release leaves the machine with no runner (today's `bootstrap.sh`). |

Each expected failure is a model counterexample. Real evidence: RunnerStaleDrop and RunnerInstallGap match the M1 logs above; RunnerNoRollback matches `bootstrap.sh` as read, not executed; for RunnerDoubleRun the resubmit path is in the logs but a concurrent second execution was not observed live. The trace for each is in `tlc-output.txt`, and the follow-up briefs are in `follow-ups.md`.

`check.sh` prints `KNOWN BUG <cfg>: <property> violated` for each expected failure and exits non-zero only if an expectation is not met.

## Run

```
~/.local/bin/heavy sh formal/woodpecker-runner/check.sh
```

Set `MAC_OPS_TLA_JAR` to use another `tla2tools.jar`. Raw TLC output stays under `$TMPDIR`.

See the [state chart](../../docs/state-charts/woodpecker-runner.md).
