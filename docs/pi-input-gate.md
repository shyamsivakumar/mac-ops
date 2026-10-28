# Pi first-message delivery

The local launcher queues the board's first brief until Pi has finished
startup and the editor accepts input. It waits for the complete paste to be
written, then releases Enter after a short settle. Pi's TUI often does not
echo the draft back to the PTY, so the gate uses a timed acknowledgement
instead of Cursor's draft-receipt match. Each board brief and each
`herdr-projects tell` follow-up goes through the same delivery cycle:
composer readiness, complete paste write, settle, then Enter. The session
does not passthrough raw stdin after the first message.

Board launches also set `PI_SKIP_VERSION_CHECK=1` so the async "Update
Available" banner does not race the first brief. User settings merge
`quietStartup: true` to hide the startup header and loaded-resource listing
(changelog notifications are still controlled by the version check).

## Install and undo

Use Python 3.9 or newer on macOS. No Python packages are required.

```sh
python3 scripts/install_pi_gate.py install
python3 scripts/install_pi_gate.py status
```

The installer preserves the existing `~/.local/bin/pi` symlink as
`pi.before-mac-ops-12` and copies the wrapper into the original PATH entry.
It records the original link and installed file hash in
`pi.mac-ops-12.json`. The vendor Node bundle stays untouched. The installed
copy does not depend on this checkout.

`./install.sh agents` runs this installer after merging Pi settings. Re-running
`./install.sh agents` is safe: an unchanged gate is a no-op, and an updated gate
script replaces the installed wrapper only.

Undo with the checked installer while this checkout is available:

```sh
python3 scripts/install_pi_gate.py uninstall
```

The equivalent direct undo for an unchanged installation is:

```sh
mv "$HOME/.local/bin/pi.before-mac-ops-12" "$HOME/.local/bin/pi"
```

## Scope and behavior

- The gate requires a Herdr board task identity, its report path, a task
  temp folder beneath `hp-<uid>`, and interactive input/output. Ordinary CLI
  use, `pi -p`, and non-board launches execute the original program directly.
- Readiness looks for Pi footer or onboarding text (`gpt-6.1-terra`,
  `thinking max`, `show full startup help`, and similar) plus raw terminal
  mode on the PTY for 250 ms.
- The startup/delivery deadline is 45 seconds and buffered input is limited
  to 1 MiB. A failed delivery exits visibly rather than forwarding a partial
  brief.

Pi upgrades can change footer text or terminal behavior; use the status
command and repeat the board smoke check after an upgrade.

## Verification

Run a throwaway board task on `pi/openai/gpt-6.1-terra` with
`worker.effort max`. Confirm the first coordinator brief reaches Pi and the
agent responds without an unsent message stuck at the prompt.

See the [state chart](state-charts/pi-input.md).
