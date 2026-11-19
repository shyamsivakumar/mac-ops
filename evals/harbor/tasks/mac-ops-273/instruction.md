# MO-251 · ticket gate asks for more threads than the tool allows, so every new gate refuses

## Goal and why
`ticket gate` refuses with an RPC error instead of gating, for every pull request it has not already seen:

```
refused: t3 call t3_thread_list failed: RPC error: {"code": -32602, "message": "Invalid parameters for tool 't3_thread_list': Expected a value less than or equal to 100   at [\"limit\"]"}
```

The T3 `t3_thread_list` tool caps `limit` at 100. `coordinator/bin/ticket` line 1260 asks for `limit: 500` in the duplicate-gate pre-check, so the call always fails and the gate is refused before any of the real checks run. Seen on 2026-11-13 on fantasy-football-toolkit #423, #425, #426 and #442. Those pull requests have no gate, so they sit on the board while the coordinator gated everything else.

## Context
- `coordinator/bin/ticket`, function `gate_conflict` (about line 1238 to 1262): reads `queue.json` for the gate id, then `dispatch-receipts.json`, then calls `t3_thread_list` with `{"allProjects": True, "limit": 500, "statuses": LIVE_STATUSES, "includeSubagents": False}` to find a live thread with the gate's title.
- The installed copy `~/.local/bin/ticket` has the same line.
- `t3mcp schema t3_thread_list` reports `limit` with `maximum: 100`. The same call with `limit: 100` returns normally.
- `coordinator/bin/coordq` already uses `limit: 100` in its own `t3_thread_list` calls, so 100 is the established value in this repo.

## Scope and non-goals
In: change that one call to `limit: 100`. If the live-thread lookup must see more than 100 threads, page it with the `cursor` the tool returns, but only if a test shows 100 is not enough; otherwise keep the single call at 100 and say so in the PR.
Out: no change to the other duplicate checks (queue item, `gatedHeads`, receipts), no change to `coordq`, no change to the title format, no new dependency.

## Design fit
`gate_conflict` owns the duplicate-gate pre-check, and the schema caps the page size. The fix is the page size, in place.

## Stated behavior change
`ticket gate` stops refusing with an RPC error on a pull request that has no gate yet, and the duplicate checks still run in the same order.

## Acceptance and proof
- Before and after on a real pull request that currently refuses: `ticket gate shyamsivakumar/fantasy-football-toolkit#442 --dry-run` prints the RPC error before the change and the normal dry-run plan after it. Paste both.
- A test that stubs `t3_call` and asserts the pre-check never asks for more than the schema maximum, so the same mistake cannot come back.
- `heavy python3 scripts/mac_ops_fast_check.py`.

## Must not cause
No regression in the duplicate checks: an already-queued gate, a recorded head, or a receipt must still refuse with the same messages.

## Data/secrets and stop conditions
No secrets. Ten-minute cap. Stop and report if `limit: 100` is not enough to see the live threads, instead of inventing a second lookup.

The repository is at `/app`. Make the change there. Do not edit test files.
