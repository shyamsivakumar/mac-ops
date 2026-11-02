# Woodpecker runner lifecycle model

`RunnerLifecycle.tla` models the self-hosted Woodpecker runner on the M1.
A job is registered, polled by a worker slot, run and reported. The agent
can be restarted or reinstalled while jobs are in flight. The model fixes
nothing. It reproduces known problems as counterexamples.

## What is modelled

- Two worker slots on one native agent process
  (`WOODPECKER_MAX_WORKFLOWS=2` from MO-72) and two tasks.
- The server queue: pending tasks, a lease owner per running task, a
  TaskStore `backup` set, and the database state of each workflow.
- What really runs on the host, which differs from the server view after
  a restart or a partition.
- The install path: kickstart, a new release that may be broken, and an
  optional rollback step.
- A fault budget (`MaxFaults = 1`) so every run is finite. Restarts,
  installs and partition expiries each use one fault.

## Source facts

- Woodpecker v3.16.0 `server/queue/fifo.go`, `resubmitExpiredPipelines`:
  a running task whose lease passed goes back to the front of pending
  without restoring the TaskStore backup. Another in-memory worker can
  poll it at once.
- Woodpecker v3.16.0 `server/queue/persistent.go`, `Poll`: the first
  successful poll deletes the backup row. A later poll of a resubmitted
  task whose backup is gone logs `not found in backup, dropping stale
  task` and returns no work. Production on the M1 uses this wrapper
  (`StaleDrop = TRUE` in the model).
- Woodpecker v3.16.0 `server/rpc/rpc.go`, `Done`: updates the workflow DB
  (`UpdateWorkflowStatusToDone`) before acknowledging the queue.
  `fifo.finished` does not check which worker holds the lease.
- Woodpecker v3.16.0 `agent/runner.go`: the cancel of the first agent
  arrives only through its gRPC Wait stream, so a slow or partitioned
  agent keeps executing. Extend failures are only logged.
- `~/Code/woodpecker-ci/scripts/bootstrap.sh` on the M1 runs `set -eu`,
  `compose up -d --force-recreate` and `scripts/verify.sh`. It has no
  automatic rollback. The plist edit and `launchctl kickstart -k` are
  also manual, with a `.before-max2` copy.
- Incident: workflow 4254 (pipeline 1449) was running when the MO-72
  reinstall restarted the agent at 2026-10-29T20:00:46-07:00. The server
  resubmitted it, dropped it as stale, and the row is still `running`.

## Configs and expected results

- `RunnerNoPartition.cfg`
  - Settings: Partition off, StaleDrop off, Rollback on.
  - Checks: NoDoubleRun, TypeOK, RunnerComesBack,
    FailedInstallRollsBack, JobsReported.
  - Expected: Pass.
- `RunnerDoubleRun.cfg`
  - Settings: Partition on, StaleDrop off.
  - Checks: NoDoubleRun.
  - Expected: Fails on bare FIFO only. A lease expires while worker 1
    still runs the task, and worker 2 polls it. Production persistence
    (`StaleDrop` on) blocks that second poll.
- `RunnerInstallGap.cfg`
  - Settings: Partition off.
  - Checks: RunnerAlwaysUp.
  - Expected: Fails. Every install or restart takes the only native
    macOS agent down (both MO-72 slots share one process), so darwin
    jobs have no runner until it returns. The real gap for workflow
    4254 was 11 seconds (agent.log 20:00:46 shutdown, 20:00:57 start).
- `RunnerStaleDrop.cfg`
  - Settings: StaleDrop on.
  - Checks: JobsReported.
  - Expected: Fails. A restart orphans a lease, the task is resubmitted
    and dropped (backup gone), and the database stays `running`
    (workflow 4254).
- `RunnerNoRollback.cfg`
  - Settings: Rollback off.
  - Checks: RunnerComesBack, FailedInstallRollsBack.
  - Expected: Fails. A broken new release leaves the machine with no
    runner (today's `bootstrap.sh`).

Each expected failure is a model counterexample. Real evidence is in
[follow-ups.md](follow-ups.md). The trace for each is in
`tlc-output.txt`.

`check.sh` prints `KNOWN BUG <cfg>: <property> violated` for each
expected failure. It exits non-zero only if an expectation is not met.

## Run

```sh
~/.local/bin/heavy sh formal/woodpecker-runner/check.sh
```

Set `MAC_OPS_TLA_JAR` to use another `tla2tools.jar`. Raw TLC output
stays under `$TMPDIR`.

See the [state chart](../../docs/state-charts/woodpecker-runner.md).
