# Follow-ups from the runner model

Traces are in [tlc-output.txt](tlc-output.txt).
Command and log evidence is in [repro-evidence.txt](repro-evidence.txt).
None of them is fixed here.

## 1. Agent restart strands a job as running (RunnerStaleDrop, JobsReported) — #36

Trace: w1 polls t1. An agent restart (a reinstall, or `scripts/watchdog.sh`
on the M1 running `launchctl kickstart -k org.woodpecker.agent`) kills w1's
run of t1. The one-minute lease expires and the server resubmits t1.
Because the TaskStore backup was deleted on the first poll and is not
restored on resubmit, `persistentQueue.Poll` drops it as stale.
The database row stays `running` and no status reaches GitHub.

Real reproduction: workflow 4254 (strategy-replay-workbench pipeline 1449)
was running on `shyams-macbook-pro-ios`. agent.log at
2026-10-29T20:00:46-07:00 shows `received sigterm termination signal` for
workflow 4254; at 20:00:57 the agent restarts with `parallel workflows: 2`.
Server path: resubmit then `not found in backup, dropping stale task`.
The `workflows` row 4254 still had `state=running`, `finished=0` on
2026-11-01. See repro-evidence.txt section C.

Fix idea: drain the agent (stop polling, wait for running workflows) before
any restart, and sweep workflows whose task has left the queue to `killed`.

Task: <https://github.com/shyamsivakumar/mac-ops/issues/36>

## 2. Install leaves darwin jobs with no runner (RunnerInstallGap) — #37

Trace: the install starts and the only native agent process goes down.
Both MO-72 slots live in that one process.

Real reproduction: agent.log shows shutdown at 20:00:46 and
`starting Woodpecker agent ... parallel workflows: 2` at 20:00:57 on
2026-10-29, an 11 second gap with no darwin runner. Any darwin job running
at that moment was killed (item 1). See repro-evidence.txt section C.

Fix idea: run the second runner as a separate agent process with its own
name, workspace and LaunchAgent (the original MO-72 brief), and restart
them one at a time after a drain.

Task: <https://github.com/shyamsivakumar/mac-ops/issues/37>

## 3. Bare FIFO lets a second runner take a job (RunnerDoubleRun) — #38

Trace: w1 polls t1. w1 misses its lease while still executing.
The server resubmits t1 to the front of pending. w2 polls t1 and both run it.

Qualification: this counterexample sets `StaleDrop = FALSE` (bare in-memory
FIFO). Production uses `persistentQueue`, so the same sequence becomes
item 1 (stale drop) instead of a second assign. The model keeps the
bare-FIFO case to document the upstream hazard if persistence is off.

Evidence:

- Source: `fifo.go` `resubmitExpiredPipelines` PushFront without restoring
  TaskStore; `persistent.go` Poll drops when backup absent
  (repro-evidence.txt D–E, G).
- Live: agent.log has repeated `failed to extend workflow lease ... task
  not found` after tasks leave `running` while the agent still extends.
  A concurrent second execution was not observed on the M1.
- TLC: RunnerDoubleRun in tlc-output.txt.

Next step: confirm on a throwaway local Woodpecker with persistence
disabled, then mitigate or raise upstream.

Task: <https://github.com/shyamsivakumar/mac-ops/issues/38>

## 4. A failed runner install has no rollback (RunnerNoRollback) — #39

Trace: both jobs finish. The install starts with a broken release and the
agent goes down. The install reaches `failed` with no agent up, and
nothing restores the old release.

Real reproduction (isolated command, no production touch):

```sh
d=$(mktemp -d)
printf old > "$d/release"
printf '%s\n' '#!/bin/sh' 'set -eu' 'printf new > "$1/release"' 'false' > "$d/core.sh"
sh "$d/core.sh" "$d"; echo "release=$(cat "$d/release")"
# => exit=1 release=new
```

That mirrors `bootstrap.sh`: `set -eu`, recreate/replace, then a failing
verify with no restore. On the M1,
`~/Code/woodpecker-ci/scripts/bootstrap.sh` lines 2, 58 and 71 are exactly
that sequence; `grep` finds no `rollback`/`restore`
(repro-evidence.txt A–B). The MO-72 plist edit was manual, with a
`.before-max2` copy and no automated revert.

Fix idea: record the current image digests and plist before the recreate,
restore them and restart when verify fails, and prove it on a throwaway
Colima profile.

Task: <https://github.com/shyamsivakumar/mac-ops/issues/39>
