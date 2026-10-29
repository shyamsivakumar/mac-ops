# Omp Cursor retry

`scripts/omp_cursor_retry.py` owns the pinned omp 18.13.3 source patch and
its private Bun 1.4.4 runner. Task-local proof copies remain available.
`scripts/install_omp_gate.py install --cursor-retry` additionally provides
an explicitly opted-in durable runner behind the existing input gate.
Production installation requires explicit approval.

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
The patch clears that variable only in the bash tool's per-command environment,
so a nested `omp` command runs as omp. The shared non-interactive environment
does not clear it, so DAP's no-Node fallback can retain Bun mode. An LSP
subprocess configured to launch the compiled omp binary was observed to
inherit Bun mode and report the Bun version instead of the omp version.
These integration paths require further execution checks.

## Durable opt-in and update survival

After separate installation approval, the command is:

```sh
python3 scripts/install_omp_gate.py install --cursor-retry \
  --retry-source "$HOME/.bun/install/global/node_modules" \
  --retry-omp "$HOME/.bun/bin/omp"
python3 scripts/install_omp_gate.py status
```

The explicit source/runtime pairing matters: the existing board launcher's
backup currently targets Tern, not the separate Bun installation containing
the patched source revision. Opt-in binds the source runner and updates to
the configured Bun installation; it does not change the backup or the vendor
binary. `--bin-dir` selects a different gate directory for isolated use.
Installing without `--cursor-retry` never activates the runner; refreshing an
already opted-in gate preserves its receipt's selection.
The installer rejects a runtime path equal to, hard-linked to, or resolving
through the managed gate, including intermediate symlink aliases, before
copying or publishing anything. The installed runner repeats this guard.

The installer copies the helper and patch into a content-addressed
`omp.cursor-retry-*` bundle beside the input gate and records its inner
launcher in the existing gate receipt. The checkout is not needed afterward.
The original input gate remains the PATH entry, with the same board identity,
PTY readiness, paste framing and Enter-release checks. Ordinary CLI tools and
their arguments are unchanged; no tools are disabled by this mechanism.

Each generation launcher embeds the managed gate's absolute path as a
shell-quoted `MAC_OPS_OMP_LAUNCHER` assignment, overriding any inherited value.
The pinned profile-alias resolver uses that path rather than its source-mode
runtime/CLI argv. Thus `omp --profile work --alias omp-work` creates an alias
back to the input gate, not an unmanaged private runtime or vendor bypass.
Opted-in board launches accept profile flags through the normal gate.

Before every normal invocation the inner launcher validates source package
version 18.13.3 and all patch preimage hashes, hashes the vendor runtime and
checks the source tree's file identities, sizes, modes and nanosecond change
times. A replacement/reinstall therefore selects a new generation even when
its version and contents are identical. Unchanged invocations reuse a checked
generation without patching again. A generation holds private copies of all
dependencies and the runtime, not symlinks back to the mutable installation.
Symlinks escaping the source tree are unsupported and rejected.

Only one launcher prepares a generation at a time (`flock`). It clones into a
same-filesystem temporary directory, rechecks upstream identity, applies the
patch, verifies postimages and Bun, records the private tree identity, then
renames the complete generation into place atomically. Existing processes
keep their old private generation. Incompatible upstream or damaged private
generations stop the launch visibly: there is no unpatched or stale-generation
fallback. An external updater does not take this lock; changes observed during
copying cause refusal and require another invocation after it finishes.

For opted-in board calls the gate creates its PTY and enters raw input
buffering immediately, while the child prepares the generation. A dedicated
inherited pipe signals completion before the child executes the source CLI.
Only then does the existing 45-second startup/input deadline begin. Early
paste bytes stay in the gate's existing bounded parser buffers; they do not
wait in a canonical-mode terminal during a slow clone. Cancellation, signals
and the 1 MiB buffer limit still stop preparation. Readiness, complete paste
write and Enter separation are still required after preparation succeeds.

Use `omp update ...` through the input gate for an upstream self-update. Only
that maintenance invocation executes the configured vendor binary with its
own directory first on PATH, so upstream's PATH-based update target resolver
cannot replace the managed input gate. Normal source execution keeps PATH
unchanged, including nested `omp` calls from tools. External Bun reinstall
commands likewise modify only the vendor install. The next normal gate call
automatically snapshots and reapplies the patch if the exact pinned revision
still matches. A new incompatible release is intentionally refused until the
patch and pinned hashes are reviewed and the user reinstalls the opt-in
bundle; running a stale 18.13.3 copy is not update survival.

Undo remains `python3 scripts/install_omp_gate.py uninstall`. It restores the
original symlink and leaves inactive receipts/bundles and generations intact.
Old generations are retained rather than deleting files used by running
processes. This requires disk space; there is no automatic garbage collector.
macOS/APFS clone support and Python 3.9+ are required. Full-tree metadata
validation adds filesystem work on every launch. The atomic rename guarantee
is publication atomicity, not power-loss durability or a transaction with an
external vendor updater. A vendor-only binary update does not refresh source
packages; mismatched source/runtime installs need explicit repair, not a
guessed patch.

## Verification

Run the [bounded gate check and runtime procedure](../.agents/skills/verify-omp-cursor-retry/SKILL.md).
The procedure covers the matched stock/patched fault matrix, write and shell
safety, the watchdog stall for write, shell and MCP frames, the shared
classifier comparison and ten live Grok turns. MO-35's raw evidence is
outside the repo in `~/.herdr-projects/reports/mac-ops/35/`.

The earlier fault-matrix/live-turn reports identify their earlier patch
hashes. The durable alias target and shell-only Bun environment fix change
the full patch identity without changing the retry/veto hunks; do not label
those old reports as executions of the newer complete installed artifact.

The current hardened durable artifact has been installed with explicit approval.
Its full reinstall flow and the alias and shell environment changes still need
end-to-end verification.

See the [state chart](state-charts/cursor-retry.md).
