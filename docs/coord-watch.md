# Coordinator board snapshots

`coord-watch --once` prints one `BOARD <json>` line. The existing lane owns all actions. The command does not start threads, change labels, install packages or schedule another cycle. The installer copies it alongside `ticket` and `overnight`, whose issue normalization and PR linking adapters it reuses.

The configured repositories come from the existing ticket config. Every open issue is included, including issues with no stage label. Each item has `repo`, `issue`, `stage`, `thread`, `pr`, `head` and `attempt`. Identity is repository plus GitHub issue number, not the display ticket number. The largest recorded builder attempt supplies the thread; queue entries use `args.clientRequestId`, and dispatch receipts use the same request ID. T3 supplies the observed thread status. The bounded dispatch log tail supplies source availability; it never proves completion.

Missing fields are null or `unknown`. Source completeness is explicit. A failed or truncated GitHub read retains previously observed issues with stage `unknown`; a complete current read can remove closed issues. A missing T3 thread never implies idle or completed. With no previous state, an unavailable repository has no discoverable items and is explicitly unknown. If several open PRs link to one issue, the greatest PR number is selected. No completion decision is made here.

## Bounds and request budget

One invocation is one cycle. GitHub reads are cached in the command's own state file for at least 300 seconds, including failed attempts. Each refresh reads at most 40 configured repositories, three pages of 100 open issues and three pages of 100 open PRs per repository. There are no per-ticket API calls or application retries. The worst case is 40 × 6 × 12 = 2,880 GitHub requests per hour across cycles sharing a state file, including failures. That leaves 2,120 of a standard authenticated 5,000-request hourly allowance for other work. It is not a reservation of the shared account quota. Repositories beyond 40 and lists reaching the page cap remain unknown. A cold start adds at most 240 calls to a rolling-hour boundary, for 3,120. Repeatedly deleting or switching state files defeats the cache budget.

T3 is read through `t3mcp call t3_thread_list -`, at most three pages per cycle. Each subprocess has a 15-second timeout, and all network collection shares a 120-second deadline. Cached GitHub rows retain only board fields and PR references, rather than issue bodies. Queue JSON sources are capped at 8 MiB; only the last 64 KiB of `dispatch.log` is read. The command writes only its state file, default `~/.coordinator/coord-watch.json`; the parent directory must already exist. The file is exclusively locked during a cycle. An interrupted state write can require restoring that file; there is no activation or queue recovery action.

## Reproduce the source proof

From the repository root, run:

```sh
timeout 300 python3 coordinator/bin/coord-watch --once --config evidence/MO-1004/config.json --fake-input evidence/MO-1004/complete.json
timeout 300 python3 coordinator/bin/coord-watch --once --config evidence/MO-1004/config.json --fake-input evidence/MO-1004/partial.json
timeout 300 python3 evidence/MO-1004/collect-proof.py
timeout 300 python3 scripts/mac_ops_fast_check.py
```

Fake mode uses the same snapshot transformation and adapters, makes no subprocess calls and writes no state. `complete.json` proves issue identity, PR/head association and latest attempt/thread selection. `partial.json` proves retention of the same issue with unknown sources. The captured outputs and review are in `evidence/MO-1004/`. Live-service and owner testing were waived by the coordinator. No live command was activated.
