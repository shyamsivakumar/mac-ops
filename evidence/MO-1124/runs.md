# MO-1078 runs (ticket MO-1330)

## Dry run on the live Mac, 2026-11-27 17:53 EST (draft, with the idle rule at 900 s)

Command: `python3 scripts/mcp_reaper.py --dry-run --idle-secs 900` (no signal sent). The shipped default has no idle rule, so the same run at 17:53 would have shown `stale_sets=0` (thread `01a21f20` had not logged `Agent loop exited` yet; it did at 18:01:24). Host: pid 23080, 24 direct children at the time.

```text
stale host=23080 set_start=17:28:59 thread=01a21f20-4924-7010-973a-56d27f01654e pen:17875,paper:17876,node_repl:17879,node_repl:17882,xcodebuildmcp:17893,xcodebuildmcp:19486
live host=23080 set_start=17:30:51 thread=01a21f21-fde3-7960-99b5-387183987936 paper:26449,node_repl:26450,node_repl:26451,pen:26453,xcodebuildmcp:26466,xcodebuildmcp:27524
live host=23080 set_start=17:39:35 thread=01a21f29-fc1c-77c1-9b60-f37b555dec7f pen:62404,node_repl:62405,paper:62406
live host=23080 set_start=17:44:23 thread=01a21f2e-6209-79f2-8ed2-54003e7fa474 paper:81055,node_repl:81056,pen:81057
unknown host=23080 set_start=17:47:52 thread=- node_repl:402
live host=23080 set_start=17:49:23 thread=01a21f32-ff4d-76e1-b7e5-32b5143ebc6d node_repl:7338
live host=23080 set_start=17:49:25 thread=01a21f32-ff4d-76e1-b7e5-32b5143ebc6d pen:7739,paper:7741,node_repl:7742,node_repl:7743,xcodebuildmcp:7756,xcodebuildmcp:9519
mcp_reaper: stale_sets=1 live_sets=5 unknown_sets=1 claude_children_kept=0 dry_run=True
```

Result: it would stop 1 set (6 processes), keep 5 sets, and leave 1 unknown process (a `node_repl` with no matching thread).

## T3 thread states beside it

Times are local (T3 reports UTC). A Codex thread matches the T3 thread created in the same second.

| Set start | Codex thread | T3 status at 17:53 | Last T3 update | Reaper verdict |
| --- | --- | --- | --- | --- |
| 17:28:59 | 01a21f20 | completed, unsettled | 17:31:23 (21 min idle) | stale, would stop |
| 17:30:51 | 01a21f21 | completed, unsettled | 17:40:07 (13 min idle) | live, kept (under 15 min) |
| 17:39:34 | 01a21f29 | completed, unsettled | 17:47:53 | live, kept |
| 17:44:23 | 01a21f2e | completed, unsettled | 17:49:23 | live, kept |
| 17:49:25 | 01a21f32 | not matched by creation second (nearest is T3 `mcp:14811218`, created 17:48:44, completed 17:51:35) | 17:51:35 | live, kept (Codex activity under 15 min) |
| 17:47:52 | none | n/a | n/a | unknown, kept (a `node_repl` that started the same second as a short-lived `Codex Computer Use` process, no thread row) |

Threads `01a21f18` (T3 settled 17:47:02) and `01a21f22` (T3 settled 17:47:03) had exited before the run, and their sets were already gone.

## Mapping rule

A set is the group of MCP children of the host that share one start second, plus their descendants (the `npm exec xcodebuildmcp` parent has a `node` child). A thread owns a set when its first row in `~/.codex/logs_2.sqlite` (filtered to the host pid) is within 3 seconds of the set start. Starting a set and starting a thread happen in the same second in every case checked. A set is stale only when every matching thread has logged `Agent loop exited` or has had no log row for `--idle-secs` (default 900). No matching thread means unknown, and unknown is kept.

## Kill path check

The SIGTERM then SIGKILL path was run against two processes started for the test: `sleep` exited on SIGTERM (code -15); a shell that ignores SIGTERM got SIGKILL after the grace period (code -9). Identity (start time plus command) is re-read before each signal.

## Real run with Shyam's go

Not run. Pending approval: record child count and swap before and after here.

## Settle job dry run, 2026-11-27 18:26 EST

`DRY=True`, `settle_idle_completed({})` against the real T3 (read only). It listed four completed threads idle between 15 and 60 minutes and would settle each, for example `mcp:2e5913a1-b19b-4709-8440-d4269e0505ee`. Threads idle over an hour (about 360 more unsettled completed threads) are left alone because Codex has already evicted them.

## Reaper dry run after the scope change, 18:26 EST

```text
live host=23080 set_start=18:01:09 thread=01a21f3d-b9fe-71c2-a268-2296d0e2f4c2 node_repl:59701,node_repl:59702,pen:59703,paper:59704,xcodebuildmcp:59717,xcodebuildmcp:60869
mcp_reaper: stale_sets=0 live_sets=1 unknown_sets=0 dry_run=True
```

## Proof, red then green

Settle job proof: `python3 -I evidence/MO-1078/proof_settle.py` (fake T3 with five threads: recent, idle, pinned, Ascend, over an hour).

- origin/main (906862ac): `scripts/mcp_reaper.py --dry-run` gives `No such file`; `lane_driver.py` has no `settle_idle_completed`, so the proof fails with AttributeError.
- head: prints `settled: ['idle']` and `PASS`. Only the thread idle between 15 and 60 minutes, unpinned and not Ascend, is settled.

## Replacement ticket

#1124 replaces #1078. Its proof command, `scripts/mcp_reaper.py --dry-run`, reads
`$HOME/.codex/logs_2.sqlite`, which the gate's temporary HOME does not have, so it
exited 2. The #1124 proof command is `python3 -I evidence/MO-1078/proof_settle.py`
(a fake T3, no live files). It exits 2 on `origin/main` (no such file) and prints
`PASS` with exit 0 on this branch, with `HOME=$(mktemp -d)`. The script stays in
`evidence/MO-1078/` because the proof command names that path.
