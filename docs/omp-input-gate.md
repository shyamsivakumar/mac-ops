# Omp first-message delivery

The local launcher queues the board's first brief until Omp has finished
startup and the editor accepts input. It waits for the complete paste to be
written, then releases Enter after a short settle. Omp's TUI often does not
echo the draft back to the PTY, so the gate uses a timed acknowledgement
instead of Cursor's draft-receipt match. Follow-up input then passes through
as raw bytes.

Board launches also set `OMP_SKIP_SETUP=1` so first-run setup does not race
the first brief. User settings merge `startup.quiet: true` to hide startup
chrome (splash and loaded-resource listing).

## Install and undo

Use Python 3.9 or newer on macOS. No Python packages are required.

```sh
python3 scripts/install_omp_gate.py install
python3 scripts/install_omp_gate.py status
```

The installer preserves the existing `~/.local/bin/omp` symlink as
`omp.before-mac-ops-14` and copies the wrapper into the original PATH entry.
It records the original link and installed file hash in
`omp.mac-ops-14.json`. The vendor binary stays untouched. The installed
copy does not depend on this checkout.

`./install.sh agents` runs this installer after merging Omp settings. Re-running
`./install.sh agents` is safe: an unchanged gate is a no-op, and an updated gate
script replaces the installed wrapper only.

Undo with the checked installer while this checkout is available:

```sh
python3 scripts/install_omp_gate.py uninstall
```

The equivalent direct undo for an unchanged installation is:

```sh
mv "$HOME/.local/bin/omp.before-mac-ops-14" "$HOME/.local/bin/omp"
```

## Scope and behavior

- The gate requires a Herdr board task identity, its report path, a task
  temp folder beneath `hp-<uid>`, and interactive input/output. Ordinary CLI
  use, `omp -p`, and non-board launches execute the original program directly.
- Readiness looks for the board worker model label in the footer (for example
  `GPT-6.1 Terra`) plus raw terminal mode on the PTY for 250 ms.
- The startup/delivery deadline is 45 seconds and buffered input is limited
  to 1 MiB. A failed delivery exits visibly rather than forwarding a partial
  brief.

Omp upgrades can change footer text or terminal behavior; use the status
command and repeat the board smoke check after an upgrade.

## Verification

Run a throwaway board task on `omp/openai-codex/gpt-6.1-terra` with
`worker.effort max`. Confirm the first coordinator brief reaches Omp and the
agent responds without an unsent message stuck at the prompt.

See the [state chart](state-charts/omp-input.md).
