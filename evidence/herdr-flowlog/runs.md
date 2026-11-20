# Herdr flow log proof

Offline harness: flowlog.js run under bun with stubbed herdr I/O (read hangs, write rejects always, write rejects once). The new copy uses a 300 ms timeout in place of 15 s so the run is short. Old copy is origin/main.

```
old | read hangs | first flush: STILL PENDING after 2s | next tick: next flush did nothing (stuck) | error lines: []
old | write rejects always | first flush: threw stale snapshot | next tick: next flush wrote the file | error lines: []
old | write rejects once | first flush: threw stale snapshot | next tick: next flush wrote the file | error lines: []
new | read hangs | first flush: returned | next tick: next flush wrote the file | error lines: ["flow log flush failed, 1 events requeued: no answer after 0.3s"]
new | write rejects always | first flush: returned | next tick: next flush wrote the file | error lines: ["flow log flush failed, 1 events requeued: stale snapshot"]
new | write rejects once | first flush: returned | next tick: next flush wrote the file | error lines: []
```

Old: a hung read leaves flushing true, so later ticks write nothing and no line is logged. New: the flush returns, the next tick writes, and one error line is printed. A single stale-snapshot rejection is retried silently.

Syntax: bun build --no-bundle on flowlog.js and main.js passes. The repo has no mod check script; scripts/mac_ops_fast_check.py proof is in check-proof.md.
