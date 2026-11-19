# MO-1057 · Tick finishes even when GitHub calls hang

## Goal and why
The coordinator tick (launchd job dev.coordinator.tick, runs every 30 minutes) was killed at its 600-second limit at 07:45 PT on 2026-11-17 (log: "tick killed after 600s", last exit 124), and the watchdog raised "tick failing" twice. Earlier ticks finished in 1 to 3 minutes. At the same time GitHub's GraphQL API was timing out from this Mac ("dial tcp ... connect: operation timed out"). Find why one tick ran 10 minutes, and stop a slow external call from eating the whole tick.

## Do
1. Read the tick's own logs for the 07:15 to 07:45 run (~/Library/Logs/coordinator/tick.log and any per-tick output the job keeps) and the tick code in mac-ops (`coordinator/`; find the tick entry the plist runs). Name the step that ran long.
2. Four hypotheses tested against that evidence: (a) a GitHub call hung on the network timeout with no client timeout; (b) the tick's agent turn itself ran long; (c) the overnight selftest or another sub-step ran long; (d) lock or queue contention with another job.
3. Fix the real cause in its owner: give every external call (gh, t3mcp, curl) a bounded timeout and let the tick finish its other work, logging which call was skipped. No change to the 600-second limit itself.

## Acceptance and proof
- The named cause with the log line.
- A simulated hung GitHub call (for example pointing one call at a blackhole address) shows the tick finishing under 600 seconds and logging the skip (paste output).
- `python3 scripts/mac_ops_fast_check.py` passes; `Builder check: PASS <full head sha>` on its own line in the PR body.

## Design fit
Change the tick's existing call helper; no second helper.

## Scope and non-goals
In: bounded external calls in the tick. Out: the tick schedule and limit.

## Must not cause
The tick skipping a whole cycle silently; touching coordinator/mods/.

## Data/secrets and stop conditions
No secrets. 20 minutes; commands under `timeout 300`; no new tickets.

## Context
The tick job is dev.coordinator.tick (launchd, every 30 minutes, killed at 600 s). Recent clean ticks took 1 to 3 minutes (06:20, 06:51). The killed one started near 07:35 PT. GitHub API timeouts were seen from this Mac at the same time and cleared by 07:50.

The repository is at `/app`. Make the change there. Do not edit test files.
