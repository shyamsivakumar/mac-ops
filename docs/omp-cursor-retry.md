# Omp Cursor retry proof

`scripts/omp_cursor_retry.py` prepares a task-local omp 18.13.3 source copy
with `scripts/omp_cursor_retry.patch` applied. It copies the installed omp
binary into the same scratch folder and uses its embedded Bun 1.4.4 to run
the patched TypeScript. It never edits `~/.bun`, PATH, the board launcher or
worker settings. Installation requires a separate approval and change.

On the requested fault matrix the patched copy recovered all 6 safe cases,
against 4 of 6 for stock omp. In all 8 unsafe cases (write, shell, and either
one followed by a read) it ended the turn with no provider request after the
fault and no duplicate side effect. Ten live Grok turns returned the exact
expected reply with no empty endings.

## Patch behavior

- Bare `ECONNRESET` counts as a transient transport failure in the provider
  retry classifier. The session classifier accepts only the exact message
  `ECONNRESET` from the `cursor-agent` API, so validation, authentication and
  abort errors keep their existing retry counts.
- Cursor keeps a shared `safety` object across checkpoint retries, HTTP/1
  fallback and model id fallback. Only local file reads and the request
  context exchange leave it safe. Every other execution request marks it
  unsafe before the handler runs.
- An unsafe turn also sets `cursorReplayUnsafe` on the assistant message.
  The outer stream watchdog in `register-builtins.ts` copies that flag and the
  `[Cursor retry blocked after non-read execution]` prefix onto its
  replacement error, so a stalled stream cannot drop the veto.
- Earlier tool calls since the last non-synthetic user message are checked
  too, and so is a prior message's flag. A write or shell call therefore
  remains unsafe after a later read.
- The session agent-end handler stops a flagged error or abort right after
  logging it, before credential handling, compaction or automatic recovery.
  `TurnRecovery` also refuses flagged messages in `isRetryableError`,
  `handleRetryableError`, `classifyResolvedInterruptedToolTurn` and
  `handleCommittedTextStreamStall`. Other helpers such as
  `isRetryableReasonlessAbort` are not guarded and rely on the earlier veto.
- A resolved local-read turn can continue after `ECONNRESET` or `ENOTFOUND`.
  Paths containing `://` are excluded because internal URL readers can run
  other handlers. Other read-only tools are conservatively excluded.

## Prepare and run

```sh
scripts/omp_cursor_retry.py check
scripts/omp_cursor_retry.py apply --root "$TMPDIR/cursor-proof"
"$TMPDIR/cursor-proof/omp" --version
"$TMPDIR/cursor-proof/omp" --model cursor/grok-4.7 --no-session -p 'Reply OK'
```

`apply` requires a destination below the current task's TMPDIR. It checks
exact upstream SHA-256 values before and after copying and exact patched
SHA-256 values after application. It rejects moved or modified source rather
than guessing where to patch. Repeating `apply` verifies the existing copy
and reports `unchanged`. Changed or damaged copies require a new destination.

The `@oh-my-pi` source packages and runtime are private copies. Other
libraries are symlinked to the installed dependencies, so a shared dependency
update during a proof run is outside the snapshot guarantee. The proof copy
is not a production installation or rollback mechanism.

The source runner needs `BUN_BE_BUN=1` for its internal worker subprocesses.
The patch sets that variable empty in the shell tool environment so a nested
`omp` command runs as omp. LSP and DAP integrations are not covered by this
proof and must be checked before installation.

## Verification

Run the [bounded gate check and runtime procedure](../.agents/skills/verify-omp-cursor-retry/SKILL.md).
The procedure covers the matched stock/patched fault matrix, write and shell
safety, the watchdog stall for write, shell and MCP frames, the shared
classifier comparison and ten live Grok turns. MO-35's raw evidence is
outside the repo in `~/.herdr-projects/reports/mac-ops/35/`.

See the [state chart](state-charts/cursor-retry.md). Worker settings remain
unchanged until a separately approved installation is verified.
