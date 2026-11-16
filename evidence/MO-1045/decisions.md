# MO-1045 recovery evidence

The lane pass now checks unsettled failed and interrupted runs in the existing lane allowlist. Receipt identity, current ticket and linked PR state, recorded PR head, all newer active receipts, and worktree membership constrain recovery. Provider-limit failures use the requested model fallback. A deterministic ticket attempt request ID lets the existing queue publish the replacement receipt. The lane ledger records submissions before settlement and limits each ticket to two relaunches per local day.

Verification on 2026-11-16:

- All overnight selftest evaluations passed, including the planted Opus spend-limit fixture. It queued Astra once and suppressed a second submission.
- Focused mocked probes passed for changed PR head, an inactive a2 followed by active a3, and a replacement on a later live-thread page.
- The direct fast check passed, including its selected syntax checks, overnight selftests, queue model check and CLI smoke check. This is the repository task check, not every test in the repository.
- Astra's single intermediate review returned FAIL. Builder fixes address its three findings; no second reviewer verdict is claimed.
- Diff-mode comment review found no new comment blocks. Deslop review found no separate cleanup worth expanding scope.

Real read-only dry pass:

```
DEAD mcp:3f53e60d-5077-4a8b-a475-54f1b25bfd7e: coordinator needed, no ticket receipt or verified worktree (model gpt-6-astra)
DEAD mcp:2bfaf463-f73b-42ec-8caf-8121cb672b09: settle, linked PR closed (model claude-opus-5-5)
```

## Left for later

The Astra staging run has no ticket dispatch receipt, linked PR, or recorded worktree. It cannot safely satisfy the required existing_worktree relaunch. The coordinator must identify its original checkout and work identity. Consequently the acceptance requirement that every real dead run print settle or relaunch is not fully met. No live thread was relaunched or settled during verification. Installation remains the coordinator's action after merge.

## Gate fix

The final gate found that worktree discovery used the lane driver's current repository. Recovery now runs git with `-C` against the target lane's canonical repository from the existing PATHS map. The existing recovery fixture checks the complete git invocation. The minor unmapped staging-run limitation remains under Left for later above. Device, handset, owner and live-service testing are waived, not failed.
