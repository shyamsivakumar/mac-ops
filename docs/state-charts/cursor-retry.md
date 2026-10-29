# Omp Cursor turn retry

The charts cover `scripts/omp_cursor_retry.patch` and the task-local copy
prepared by `scripts/omp_cursor_retry.py`.

## One user turn

```mermaid
stateDiagram-v2
    [*] --> Clean
    Clean --> Progress: text or other server progress
    Clean --> LocalRead: local read requested
    Progress --> LocalRead: local read requested
    Clean --> Unsafe: any other execution requested
    Progress --> Unsafe: any other execution requested
    LocalRead --> Unsafe: any other execution requested
    Clean --> Retry: transient network error
    Progress --> Retry: transient error with fresh checkpoint
    LocalRead --> Retry: transient error with fresh checkpoint
    LocalRead --> Continue: transient error after reads have results
    Retry --> Clean: new attempt, safety object retained
    Continue --> Clean: session continuation, prior history checked
    Unsafe --> Unsafe: later read or checkpoint
    Unsafe --> Failed: provider error, session recovery vetoed
    Unsafe --> Failed: watchdog error keeps cursorReplayUnsafe
    Progress --> Failed: no safe recovery available
    Failed --> [*]
```

The provider sets `safety.unsafe` and `cursorReplayUnsafe` before
dispatching any execution other than local `readArgs`, `piReadArgs` or the
request context exchange. MCP, shell, write, delete, edit, grep, ls and
unknown execution frames are unsafe. A read path containing `://` is unsafe
too.

The checkpoint retry, HTTP/1 fallback and model id fallback receive the same
object. The next provider call also scans tool calls and message flags since
the most recent non-synthetic user message. Prior non-read calls keep the
turn unsafe.

Unsafe terminal errors carry `[Cursor retry blocked after non-read
execution]` and `cursorReplayUnsafe` into `agent-session.ts`. When the outer
watchdog in `register-builtins.ts` replaces a stalled stream's error, it
copies both from the last partial message. The agent-end handler stops a
flagged error or abort before credential handling, compaction or automatic
recovery, and the main `TurnRecovery` retry and continuation methods refuse
flagged messages. Safe completed-read
failures can continue through `turn-recovery.ts`.

## Task-local proof copy

```mermaid
stateDiagram-v2
    [*] --> CheckSource
    CheckSource --> Refuse: upstream file hash changed
    CheckSource --> CheckExisting: destination exists
    CheckExisting --> Reuse: manifest and copied hashes match
    CheckExisting --> Refuse: destination differs or is damaged
    CheckSource --> Copy: new destination inside task TMPDIR
    Copy --> Patch: private source and runtime copied
    Patch --> Ready: patched hashes and Bun 1.4.4 match
    Patch --> Refuse: patch or runtime differs
    Ready --> [*]
    Reuse --> [*]
    Refuse --> [*]
```

There is no installed launcher or automatic update hook. A later installation
needs separate approval. The [verification skill](../../.agents/skills/verify-omp-cursor-retry/SKILL.md)
checks all eight combinations of the provider gate's three boolean inputs,
rejects a removed-unsafe-guard mutation, and names the runtime proofs for the
watchdog and the shared classifiers.
