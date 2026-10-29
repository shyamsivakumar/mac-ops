# Omp Cursor turn retry

The charts cover `scripts/omp_cursor_retry.patch`, its task-local proof copy
and the explicitly opted-in durable runner installed behind the input gate.

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

## Durable launcher and upstream replacement

```mermaid
stateDiagram-v2
    [*] --> InputGate
    InputGate --> Original: no opt-in receipt
    InputGate --> RetryBundle: opted-in receipt
    RetryBundle --> VendorUpdate: update command
    VendorUpdate --> VendorReplaced: upstream installer succeeds
    VendorUpdate --> Refuse: upstream installer fails
    VendorReplaced --> InputGate: next actual launcher invocation
    RetryBundle --> LockedCheck: normal invocation, acquire flock
    LockedCheck --> Refuse: upstream version, hashes or tree incompatible
    LockedCheck --> CheckGeneration: unchanged upstream identity
    CheckGeneration --> SourceCLI: private generation intact
    CheckGeneration --> Refuse: private generation damaged
    LockedCheck --> Staging: new compatible installation identity
    Staging --> Refuse: copying raced updater or verification failed
    Staging --> Publish: private dependencies, patch and runtime verified
    Publish --> SourceCLI: atomic rename of complete generation
    SourceCLI --> [*]
    Original --> [*]
    Refuse --> [*]
```

For opted-in interactive board calls, the outer gate creates its PTY and
enters raw input buffering while its child prepares the private generation.
The child helper signals a dedicated inherited pipe only after validation
and publication. The signal starts/rebases the existing startup and pending
input deadlines; only then can normal composer readiness advance delivery.
Bracketed-paste support is advertised after raw mode is established.
No opt-in still executes the original program through the ordinary gate.

```mermaid
stateDiagram-v2
    [*] --> Preparing: opted-in board call, raw input enabled
    Preparing --> Preparing: preserve framed input, withhold all user bytes
    Preparing --> Starting: helper completion pipe signals ready
    Preparing --> Closed: cancellation, signal, buffer limit or helper failure
    Starting --> Ready: composer marker and raw child stable
    Ready --> Writing: complete framed paste available
    Writing --> Acknowledgement: all paste bytes written
    Acknowledgement --> Separation: Omp acknowledgement or settle fallback
    Separation --> Waiting: release held Enter after separation
    Waiting --> Starting: next brief
    Closed --> [*]
```

`Preparing` uses the existing `startup`/parser buffers rather than a second
input path. Its completion signal is not composer readiness and does not
release Enter. The existing Cursor ordering model does not model this
preparation pipe, Omp's timed acknowledgement fallback or alias generation;
these boundaries require real task-local PTY and process-execution checks.

The bundle lives beside the managed gate, outside the vendor install. It
contains its own helper, patch and recorded source/runtime paths. Its
`update` branch delegates to the configured vendor binary with that
binary's directory first on PATH only for maintenance, avoiding the
upstream updater's PATH-based selection of the managed gate as its target.
Normal invocations preserve PATH. External reinstalls need no hook: the next
gate call detects changed tree identities and prepares a generation.

Preparation is serialized and publication is atomic, but the external
updater does not take the launcher lock. Changed upstream identity during
copying refuses rather than publishing a mixed snapshot. Complete old
generations remain available to already-running processes; new invocations
never fall back to them when upstream is incompatible. Uninstall restores
the original symlink and leaves inactive bundles and receipts.

The [verification skill](../../.agents/skills/verify-omp-cursor-retry/SKILL.md)
checks all eight combinations of the provider gate's three boolean inputs,
rejects a removed-unsafe-guard mutation, and names the runtime proofs for the
watchdog and the shared classifiers.
