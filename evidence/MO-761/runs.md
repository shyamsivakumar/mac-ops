# MO-761 runs

## Probe design

- The probe launches a scratch thread titled `probe <identity>` on the blocked provider (message "Reply with the word ok.") through `t3_call`, which skips the blocked-model refusal in `with_model`. This is the launch coordq already makes.
- Success is a completed run whose last assistant reply contains the word "ok". coordq reads a thread the way `quota_failure` and the gate reader do: `t3_thread_read`, the latest run's status, the last `assistant_message` item. It polls every 5 seconds, 18 reads at most (90 seconds). A failed run, a wrong reply, a launch refusal, a launch with no result and a timeout all keep the block.
- The thread is archived after the read, success or failure, with `t3_thread_organize {action: "archive"}`. coordq had no archive call before; `t3mcp schema t3_thread_organize` lists `archive` as an action. If archiving fails the thread keeps its `probe <identity>` title.
- The check time (`blocked_at`) is written before the launch, so a failure waits a full interval, and a second dispatch run skips the provider while the first still polls.
- Default interval 30 minutes (`COORDQ_PROBE_MINUTES`), at most one provider per dispatch run.
- Where it runs: dispatch runs every 30 seconds as its own launchd job (a job does not overlap itself). The probe runs after the drain and the refill, with the queue lock released, so a probe holds only the next dispatch run, for at most 60 seconds of launch plus 90 seconds of polling, once per 30 minutes per blocked provider. The 30-minute coord-tick would equal the probe interval and sits in another script, so dispatch stays the host.
- The stubs replace `t3_call`; no provider is called.

## Ticket proof command (adapted: run from the worktree, temp COORDQ_DIR)

### origin/main
```
AttributeError: module 'models' has no attribute 'stale_blocks'
```

### PR branch
```
['openai-api:gpt-6.2-astra']
```

## Selftest case `provider_until`

The new selftest copied onto an origin/main checkout, then on the branch. It asserts a block whose `until` has passed still blocks, and drives `probe_one_block` with stubbed t3 calls: a completed "ok" reply (also "Ok." on a manual entry) unblocks and archives; an accepted launch with a failed run keeps the block, writes a fresh `blocked_at` and archives; a completed run with another reply keeps it and archives; a run still running after 18 reads keeps it and archives; a refused launch keeps it; a second run inside the interval makes no call; a fresh `blocked_at` makes no call. Archive calls are asserted by name in each case.

### origin/main
```
  File "/private/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmp.VtnKzq0cua/main/coordinator/overnight/selftest.py", line 85, in exact
    raise AssertionError(f"expected {expected!r}, got {actual!r}")
AssertionError: expected True, got False
```

### PR branch
```
provider_until: PASS
```

## Dry run writes nothing

`cmd_dispatch` with `dry_run=True`, a stale block, `t3_call` set to raise, temp dirs:
```
dry run: t3 calls 0, block file unchanged: True , journal rows: 0
```

## Unit module (existing, updated to the new rule)
```
Ran 16 tests in 0.030s

OK
```

## Gate fixes (round 2)

1. A manual block is never probed. `stale_blocks` lists only entries whose `expiry` is finite (a provider block with `expires_at`, or an old one with `until`); an entry with neither is manual and stays until an operator removes it. Selftest `provider_until`: a `{"by": "manual"}` entry with a stubbed completed "Ok." reply makes no t3 call and keeps its block. Unit test `test_stale_blocks_lists_entries_not_set_or_probed_recently` now holds a manual entry that is not listed.
2. One monotonic deadline for the whole probe. `probe_one_block` sets `deadline = monotonic() + PROBE_WAIT - PROBE_ARCHIVE_WAIT` (85s); the launch and every read get `min(60, time left)` as their subprocess timeout, the poll sleep is capped at the time left, and the archive call gets 5s, so the probe ends inside 90s. Selftest hang case with a fake clock (read stub advances the clock by the timeout it was given and fails):
```
probe elapsed (fake) <= 90: True, longest read timeout <= 60: True, thread archived: True
```
A running-forever reply now takes 17 reads (was 18).

The new selftest ran against the previous code first and failed:
```
AssertionError: expected ([], None), got (['t3_thread_launch', 't3_thread_read', 't3_thread_organize'], None)
```
and passes on the branch (`provider_until: PASS`). The first fast check here on 0ff78882 failed two existing unit tests (stale list with a manual entry; `t3_call` default timeout bound at definition so `T3MCP_TIMEOUT` patching stopped working). Both are fixed in 7c0496b5, and the fast check passed on the M1 (this Mac had 3 waiting).
