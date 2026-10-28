# Cursor first-message delivery

The local launcher queues the board's first brief until Cursor has drawn its composer and enabled raw terminal input. It waits for the complete paste to be written and for the draft or its counted paste receipt to appear before releasing Enter, with a 300 ms pause. At that transition it also forwards any incomplete parser tail in order. Follow-up input then passes through the same session as raw bytes, without parsing or waiting for a complete escape sequence.

## Install and undo

Use Python 3.9 or newer on macOS. No Python packages are required.

```sh
python3 scripts/install_cursor_gate.py install
python3 scripts/install_cursor_gate.py status
```

The installer preserves the existing `~/.local/bin/cursor-agent` symlink as `cursor-agent.before-mac-ops-1` and copies the wrapper into the original PATH entry. It records the original link and installed file hash in `cursor-agent.mac-ops-1.json`. The vendor executable and Herdr Projects plugin stay untouched. The installed copy does not depend on this checkout.

The board's adapter maps Cursor to `cursor-agent`, and Herdr launches that program in the worker shell. Replacing the existing PATH entry covers both shell lookup and clients that retain that entry's absolute path. No shell profile or board default needs changing.

Undo with the checked installer while this checkout is available:

```sh
python3 scripts/install_cursor_gate.py uninstall
```

The installer refuses to overwrite a changed launcher or backup. The equivalent direct undo for an unchanged installation is:

```sh
mv "$HOME/.local/bin/cursor-agent.before-mac-ops-1" "$HOME/.local/bin/cursor-agent"
```

The inactive JSON receipt remains. Existing sessions continue; new launches use the restored vendor link. If Cursor has updated the launcher since installation, inspect that change before restoring the older backup.

## Scope and behavior

- The gate requires a Herdr board task identity, its report path, a task temp folder beneath `hp-<uid>`, interactive input/output, and the board's known launch flags. Ordinary CLI commands, headless invocations, positional prompts and non-board launches execute the original program directly.
- Full-access board launches gain `--trust` for their assigned workspace. Auto-review launches without explicit trust pass through unchanged. The wrapper does not edit Cursor settings files or board defaults.
- The proxy advertises bracketed-paste support while it queues the first brief. It forwards terminal query replies and cancellation separately from pasted content. It preserves paste bytes and the original Enter encoding, including kitty keyboard sequences.
- The composer markers are `Plan, search, build anything` and `Add a follow-up`. Readiness also requires canonical input mode to be off for 250 ms. The first draft check uses the final 80 non-whitespace characters in output observed after the complete paste was written. Cursor folds long multiline input into a `[Pasted text #N +L lines]` receipt; its line count must match the complete captured paste.
- The startup/delivery deadline is 45 seconds and buffered input is limited to 1 MiB. An idle ready composer and an agent that has accepted its first brief have no wrapper runtime deadline. After release, terminal output is relayed with stdout only (no parser, bracketed-paste refresh, or visibility scan) and a longer `select` timeout until the user starts another delivery. A failed delivery exits visibly rather than forwarding a partial brief.

The wrapper does not retry the brief. Cursor upgrades can change its markers, terminal behavior or launcher link; use the status command and repeat the board smoke check after an upgrade. Draft matching is an observation of Cursor's output, not a vendor acknowledgement API.

## Verification

Run the actual parser against generated input chunkings:

```sh
python3 -B verification/verify_cursor_protocol.py
```

Run the finite ordering model with an existing Java/TLC installation:

```sh
heavy python3 verification/check_cursor_model.py
```

The defaults use Homebrew OpenJDK 17 and the wiki's `runtime/tla/tla2tools.jar`. Set `MAC_OPS_JAVA_BIN` and `MAC_OPS_TLA_JAR` to use existing alternative installations. The runner puts JVM extraction, state graphs, negative traces and receipts beneath `TMPDIR`; it installs nothing.

The model covers one brief, one Enter, two abstract paste-write chunks and three acknowledgement-delay ticks. The unsafe configuration must fail specifically on `ReleaseAfterAcknowledgement`. It does not prove Cursor's readiness labels, Herdr process recognition, operating-system I/O or subsequent agent work. Verify those through the real board flow: five serial throwaway tasks titled `cursor smoke ...`, each with a distinct first-response token and follow-up sent through `herdr-projects tell`. Capture the assistant response lines and wrapper process identity, then finish and archive only those tasks.

See the [state chart](state-charts/cursor-input.md) and [verification skill](../.agents/skills/verify-cursor-input/SKILL.md).
