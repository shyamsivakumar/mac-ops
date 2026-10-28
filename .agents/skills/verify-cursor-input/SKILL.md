---
name: verify-cursor-input
description: Verify Cursor board startup buffering, paste framing, draft acknowledgement, and Enter ordering after changing the local launcher or its lifecycle.
---

# Verify Cursor first-message delivery

Use this skill when changing `scripts/cursor_agent_gate.py`, its installer, readiness labels, terminal I/O, draft acknowledgement or child cleanup. Read `docs/state-charts/cursor-input.md` and `docs/cursor-input-gate.md` first.

## Coverage record

- Source sync commit: `7555e98dbc620a4a931585d6f1901bcbdbedb015`.
- Cursor gate source SHA-256: `3c7be9bcc699c8ed67510a970ec239e0e112334bd406e667164f16468f95c5f2`.
- `Input.feed` preserves framed payload bytes across input chunks, separates terminal replies from keyboard input and treats cancellation inside pasted text as data.
- `Visible.feed` excludes CSI and control strings from readiness and acknowledgement text. `draft_seen` accepts a body suffix or a folded paste receipt with the captured line count.
- The model maps `Ready` to the composer/raw-mode guard, `Queue` to `route`, `Write` to `paste_left` and `written_at`, `Echo` to a fresh draft observation, `Tick` to the monotonic separation delay, and `Release` to `transparent`. `SendEnter`, `Cancel` and `Timeout` cover the first delivery only.

The promise is that first-paste bytes wait for readiness and complete framing, and Enter waits for a full write, fresh draft observation and the separation delay. At release, the parser tail follows held input, and later input bypasses the parser. Breaking the promise can drop a brief or leave it unsent in the composer.

## Run

1. Read every change to the covered source since the sync commit. Confirm that each model action still corresponds to the code. Do not move the sync commit when the check is blocked or when the model no longer describes the code.
2. Run the actual parser and output handling against generated chunk boundaries:

   ```sh
   python3 -B verification/verify_cursor_protocol.py
   ```

   The checker enumerates all two-cut partitions of its finite byte/control traces. It includes Unicode, multiline input, paste boundaries, a cancellation byte inside and outside the paste, OSC exclusion, terminal query replies, and folded-receipt line counts. It is a bounded input check, not a proof over arbitrary messages.
3. Run the ordering model through the resource gate:

   ```sh
   heavy python3 verification/check_cursor_model.py
   ```

   Use existing Java and TLC installations. Defaults are Homebrew OpenJDK 17 and `~/Code/llmwiki/runtime/tla/tla2tools.jar`; the environment variables in the operating guide select alternatives. Install nothing automatically. The runner keeps JVM extraction, graphs, traces and receipts under `TMPDIR`.
4. Require a successful safe model and an unsafe variant that exits 12 specifically on `ReleaseAfterAcknowledgement`. Replay its counterexample: the body write is incomplete, an early echo arrives, the delay passes, and an unguarded release forwards held input. The `written_at` guard must rule out that sequence.
5. If parser behavior changed, make a scratch source copy beneath `TMPDIR`, deliberately drop a payload byte in `Input.feed`, and require the same parser command to reject it. Never inject the mutation into the installed launcher. Keep or retire the scratch copy through the task's normal temp cleanup.
6. Check the actual wrapper through a PTY with a disposable raw-mode echo child. The child must emit the composer marker and echo the complete initial framed paste to acknowledge it. Require exact initial paste and Enter bytes. Check a standalone Escape after release and another queued as an incomplete parser tail before release: each must reach the child within a 600 ms observation window before any later key is sent. Then send x, byte-fragmented arrow sequences, Ctrl+C, later bracketed paste and encoded Enter, and require exact byte order. Run through `heavy`, keep the child and receipts under task temp, and close/reap every process. A copy of the old parser-after-release implementation must fail this check; do not mistake passing parser-only checks for coverage of this main-loop branch.
7. Exercise the real terminal path with an authorized disposable pane or board batch. Verify the foreground Python wrapper path and immutable source hash, Cursor recognition, a short first brief, a multiline brief large enough to become `[Pasted text #N +L lines]`, a follow-up in the same session, and cleanup. A vendor process that bypassed the wrapper does not count.
8. When the task authorizes board acceptance, run five serial throwaway tasks with titles beginning `cursor smoke`, each answering its first brief and a `herdr-projects tell` follow-up. Preserve actual assistant response lines and wrapper identity before finishing and archiving only those owned tasks. Respect production priority and board capacity; do not change global worker settings or revive a task the coordinator stopped.

## Bounds and failure handling

The ordering model has one brief, one Enter, two abstract paste-write chunks and three acknowledgement-delay ticks. Readiness and draft acceptance are observations of an external program. The model checks ordering, not the truth of those observations, OS I/O, process detection, arbitrary retries, subsequent agent work or progress. Live checks cover those bounded paths. The raw-input handoff is outside the first-delivery model and requires the PTY boundary check in step 6. The first-delivery ordering model and its bounds remain unchanged by that handoff.

On a mismatch, distinguish model drift from a source bug before editing either. Keep failures visible and never weaken an invariant to make a run pass. A passing parser or model check does not substitute for the live terminal or board flow. Update the state chart, mapping, source hash and sync commit only after inspecting the new source and running the relevant checks. Use `maintain-formal-verification-skill` when later changes skipped that review.
