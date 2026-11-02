# Follow-ups from the runner model

Each item is one small task for the coordinator to file. Traces are in [tlc-output.txt](tlc-output.txt). None of them is fixed here.

## 1. Agent restart strands a job as running (RunnerStaleDrop, JobsReported)

Trace: w1 polls t1. An agent restart (a reinstall, or `scripts/watchdog.sh` on the M1 running `launchctl kickstart -k org.woodpecker.agent`) kills w1's run of t1. The one-minute lease expires and the server resubmits t1. The server then drops it as stale. The database row stays `running` and no status reaches GitHub.

Real reproduction: workflow 4254 (strategy-replay-workbench pipeline 1449) was running on `shyams-macbook-pro-ios`. The MO-72 change of `WOODPECKER_MAX_WORKFLOWS` from 1 to 2 restarted the agent at 2026-10-30T03:00:46Z (agent.log `received sigterm termination signal`). The server logged `queue: resubmitting expired task 4254` at 03:01:40Z and `pull queue item: 4254: not found in backup, dropping stale task` at 03:10:45Z. The `workflows` row 4254 still had `state=running`, `finished=0` on 2026-11-01.

Fix idea: drain the agent (stop polling, wait for running workflows) before any restart, and sweep workflows whose task has left the queue to `killed`.

## 2. Install leaves darwin jobs with no runner (RunnerInstallGap, RunnerAlwaysUp)

Trace: the install starts and the only native agent process goes down. Both MO-72 slots live in that one process.

Real reproduction: agent.log shows shutdown at 03:00:46Z and `starting Woodpecker agent ... parallel workflows: 2` at 03:00:57Z on 2026-10-30, an 11 second gap with no darwin runner. Any darwin job running at that moment was killed (item 1).

Fix idea: run the second runner as a separate agent process with its own name, workspace and LaunchAgent (the original MO-72 brief), and restart them one at a time after a drain.

## 3. An expired lease lets a second runner take the same job (RunnerDoubleRun, NoDoubleRun)

Trace: w1 polls t1. w1 misses its lease while still executing, because it is slow or its gRPC link is down. The server resubmits t1 to the front of pending. w2 polls t1 and both run it on the same host.

Evidence: Woodpecker v3.16.0 `server/queue/fifo.go` `resubmitExpiredPipelines` pushes the task to the front of pending and deletes it from running. `agent/runner.go` cancels the first run only when its Wait stream returns, and only logs Extend failures. The resubmit path fired on the M1 for task 4254, and agent.log has 20 `failed to extend workflow lease ... task not found` lines. A concurrent double run was not observed live. Forcing one needs a partitioned agent, which would disrupt production CI.

Next step: confirm it with a throwaway local Woodpecker server and agent, then choose a mitigation or raise it upstream.

## 4. A failed runner install has no rollback (RunnerNoRollback, RunnerComesBack and FailedInstallRollsBack)

Trace: both jobs finish. The install starts with a broken release and the agent goes down. The install reaches `failed` with no agent up, and nothing restores the old release.

Real reproduction by reading the code on the M1: `~/Code/woodpecker-ci/scripts/bootstrap.sh` runs `set -eu`, `compose build --pull`, `compose up -d --force-recreate` and `scripts/verify.sh`, with no restore step. The README's rollback is manual. The MO-72 plist edit was manual, with a `.before-max2` copy and no automated revert. The script was not run with a broken release, because that is a production change.

Fix idea: record the current image digests and plist before the recreate, restore them and restart when verify fails, and prove it on a throwaway Colima profile.
