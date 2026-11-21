# MO-761 runs

Probe choice: the probe is a `t3_thread_launch` of a scratch thread on the blocked provider with the message "Reply with the word ok." (the launch call coordq already makes, sent through `t3_call` so the blocked-model refusal in `with_model` does not stop it). UNCERTAIN: the launch returns when the run starts, so a provider that accepts the launch and fails inside the run counts as recovered; the next failure re-blocks it through the existing quota path. Default interval: 30 minutes (`COORDQ_PROBE_MINUTES`), at most one provider probed per dispatch run. Failed probes journal `provider_probe_failed` and refresh `blocked_at`, so the next probe of that provider is N minutes later. The proof stubs `t3_call`; no provider is called.

## Ticket proof command (adapted: run from the worktree, models.json from the checkout)

### origin/main 475627f9
```
AttributeError: module 'models' has no attribute 'stale_blocks'
```

### PR branch
```
['openai-api:gpt-6.2-astra']
```

## Lapsed block clears on time alone on origin/main; needs a stubbed probe on the branch

Case: `provider_until` in coordinator/overnight/selftest.py (new version copied onto an origin/main checkout, then the branch). It writes a block whose until is in the past and asserts it still blocks; on the branch it also drives `probe_one_block` with `t3_call` stubbed: success clears (also for a manual entry), failure keeps the block and writes a fresh `blocked_at`, a second run inside the interval makes no second call, and a fresh `blocked_at` makes no call.

### origin/main
```
  File "/private/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmp.qECe6UDKK7/main/coordinator/overnight/selftest.py", line 85, in exact
    raise AssertionError(f"expected {expected!r}, got {actual!r}")
AssertionError: expected True, got False
```

### PR branch
```
provider_until: PASS
```

## Unit module (existing, updated to the new rule)
```
Ran 16 tests in 0.048s

OK
```
