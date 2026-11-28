# MO-1330 root cause: MCP server sets outlive their thread

Date: 2026-11-27. Host: `codex app-server -c thread_unload_delay_secs=0` (pid 23080, started by T3). Codex 0.172.0.

## Verdict

The owning layer is T3, with the Coordinator settle flow beside it. Codex behaves as documented. A T3 thread keeps its Codex subscription after its run completes. It drops the subscription when T3 settles the thread, or (INFERRED from one thread, see theory 2) after about 30 minutes without activity. Until then Codex holds the thread loaded and its MCP set stays alive. The fix is for T3 to unsubscribe (or archive) a thread when its run completes and to resume it on the next message. With `thread_unload_delay_secs=0`, Codex then unloads it at once and closes its MCP servers.

Decision (Shyam, 27 Nov): the Coordinator settles completed T3 threads 15 minutes after their run, through T3's own settle action (`settle_idle_completed` in `coordinator/overnight/lane_driver.py`), so Codex unloads the thread and closes its set. `scripts/mcp_reaper.py` only reports. It lists sets that look stale (every matching thread has logged `Agent loop exited`) with the evidence, and sends no signal. The gate on PR #1088 found that start-time matching alone can tie a resumed thread's set to a different, exited thread, so it must not be the basis for a kill.

## Theory 1: the config key is wrong or ignored

Result: refuted for the key, and it explains the leak.

- `codex --version` prints `codex-cli 0.172.0`. The binary contains the `thread_unload_delay_secs` field (`strings` on the app-server binary).
- Upstream schema (openai/codex, `codex-rs/core/config.schema.json`): "Seconds a thread must have no subscribers and no activity before app-server unloads it. Defaults to 60; zero unloads immediately."
- Upstream `thread_lifecycle.rs` computes the unload target only when `has_subscribers` is false and the thread is inactive. A thread with a subscriber never unloads, whatever the delay.
- Pid 23080 logs `clearing thread listener during thread-state teardown ... had_listener=true` at every thread end. T3 held a listener on every thread until teardown.

## Theory 2: T3 never ends or unloads threads

Result: partly true. T3 ends threads late.

- Over the retained log window, `Agent loop exited` (Codex shutdown of a thread) appears for 16 threads in one hour. T3 does end threads.
- Completed threads stay loaded until T3 settles them or an idle timer fires. In the `t3_thread_list` read, T3 threads that were `completed` and `settled` show an `updatedAt` equal to the Codex exit second (T3 `mcp:0a4c4802...` settled 17:47:02, Codex thread `01a21f18` exited 17:47:02; T3 `mcp:launch:7977ca...` settled 17:47:03, Codex `01a21f22` exited 17:47:03).
- Codex thread `01a21f14` last had activity at 17:19:54 (state db `updated_at`) and exited at 17:49:54, exactly 30 minutes later, with its T3 thread still `completed`, not settled.
- Thread `01a21f20` was idle after 17:31:23 and still held a full MCP set at 17:52. The prediction was that it exits at 18:01:23. It logged `Agent loop exited` at 18:01:24 (30:01 after its last update) and its set pids were gone at the next sample. T3 therefore evicts a completed thread after 30 minutes of idle time, and holds it until then.

## Theory 3: Codex unload drops the thread but not its MCP clients

Result: refuted.

- Thread `01a21f22` (set started 17:31:42, pids 30917 to 30933) logged `Agent loop exited` at 17:47:03. A sample taken at 17:47:54 showed none of its pids alive, and the ps list never showed them again.
- Sixteen threads exited in the last hour. At 17:53 every set under pid 23080 maps to a thread that had not exited, and no set predates the oldest live thread (set start times match thread start times to the second).
- The streamable HTTP MCP clients log `delete session success` at the same instant (17:39:22 for thread `01a21f0a`).

## Theory 4: MCP servers ignore stdin close

Result: refuted. I launched my own fresh copy of each server with stdin from a pipe and closed it.

| Server | Exit after stdin close |
| --- | --- |
| Paper `paper mcp` | 0.2 s, code 0 |
| Pen `mcp-server-darwin-arm64` | 0.2 s, code 0 |
| `node_repl --require-browser-access` | 4.7 s |
| `node_repl` | 4.2 s |
| `npx xcodebuildmcp mcp` | 8.5 s, its whole process group gone |

## Upstream issue text (draft, not filed)

Title: Settle or unsubscribe completed threads so Codex can unload them and close MCP servers

Body: T3 starts one Codex thread per task through `codex app-server -c thread_unload_delay_secs=0`. Each thread starts its own stdio MCP set (4 to 6 processes). When a run completes, T3 keeps its thread subscription, so Codex never unloads the thread and its MCP set stays alive until the thread is settled or an idle timer ends it about 30 minutes later. With 30 or more loaded threads this reached 30 Paper and 34 Pen servers and 54.6 GB of swap. Codex closes the MCP clients correctly on unload (observed: set exits within seconds of `Agent loop exited`). Request: after a run reaches `completed`, call `thread/unsubscribe` and resume the thread on the next message.

## Follow-up options

- Codex 0.172.0 contains the `mcp_2026_07_28` feature with stdio sharing, which upstream tests as one stdio server shared across threads. It was not tried here and would cut the set count without touching T3.
- The Coordinator can settle completed T3 threads on a short timer.

## Settle and resume proof (throwaway thread)

Thread `mcp:208f882a-28d0-4150-9e51-6e88d47cc9df` (Codex `01a21f50-d4d9`), a scratch thread created for this proof.

1. 18:22:01 the run starts and a full set starts (pids 82354 to 82357). The agent lists `mcp__node_repl__js`, `js_reset` and `js_add_node_module_dir`.
2. T3 `settle` at about 18:23:18. Codex logs `Agent loop exited` at 18:23:18 and the set pids are gone at 18:23:36.
3. `t3_thread_send` to the settled thread. Codex logs `thread/resume` at 18:23:45, a new Paper process starts at 18:23:45 and a `node_repl` at 18:24:07 on the first tool call. The agent calls the `node_repl` `js` tool with `1+1` and replies `2`.

A settled thread accepts a new message and comes back with working MCP tools.

Limits: a resumed thread's set starts at resume time, while the reaper maps a set to the first log row of its thread. A resumed set therefore maps to no thread and the reaper keeps it as unknown. The settle job is what closes those.
