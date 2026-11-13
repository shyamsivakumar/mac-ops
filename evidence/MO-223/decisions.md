# MO-223 decisions

Overnight runner spec part T12: the launchd job that fires the overnight
shift. One job, `dev.coordinator.overnight`, starts the shift at 22:30 PT
and writes the morning report at 06:30 PT. The job is installed by the
mac-ops installer and it runs in dry-run mode, so a night does no work and
the morning report is the only file it writes.

Run id: `ticket:shyamsivakumar/mac-ops#191:a1`. Refs #191.

## What landed

- `coordinator/launchd/dev.coordinator.overnight.plist`: the new job.
  - `Label` `dev.coordinator.overnight`.
  - `ProgramArguments`: `~/.local/bin/overnight shift --dry-run`.
  - `StartCalendarInterval`: 22:30 and 06:30 (the spec's start and report
    times).
  - No `RunAtLoad`: a night does not start at every boot.
  - The log is `~/Library/Logs/coordinator/overnight.log`.
- `coordinator/overnight/overnight`: a new `shift` subcommand in the same
  module as `intake` and `report`.
  - The command decides which part of the night it is from the PT clock:
    22:30 starts the shift, 06:30 writes the morning report, any other
    hour does nothing and exits 0.
  - `--at start` or `--at report` forces a part, so a person can run one
    part by hand without waiting for the clock.
  - In dry-run mode the start reads the board and writes nothing, and the
    report writes `receipts/morning-YYYY-MM-DD.md` and nothing else. That
    is the acceptance: a dry run writes only the report.
  - Without `--dry-run` the start refuses and says that the arm and tick
    parts (T4, T5) are not built, rather than pretending to work a shift.
- `install_coordinator.py`: the installer already copies every plist in
  `coordinator/launchd/`, so the job is installed by the existing
  installer. The install message now names the overnight job and the
  exact `launchctl bootstrap` line, because the installer writes the
  plists and leaves the loading to the operator.
- `coordinator/overnight/README.md`: the contract names the `shift`
  command, the two times the job fires and what each one does.
- `evidence/MO-223/launchctl-print.log`, `evidence/MO-223/kickstart-run.log`,
  `evidence/MO-223/dry-run-start.log`, `evidence/MO-223/dry-run-report.log`:
  the proof runs.
- `evidence/MO-223/decisions.md`: this file.

Not touched: the merge, push and slot-cap rules, the Ascend rules, the
coordq queue, the tick job, the existing coordinator jobs, and every
existing test or check. No existing test or check was weakened.

## Decisions

### 1. One job, and the clock picks the part

- **The decision**: The plist has one `ProgramArguments` and two
  `StartCalendarInterval` entries, so the command itself decides whether
  it is the 22:30 start or the 06:30 report. `overnight shift` reads the
  PT hour and runs the matching part.
- **The gap**: launchd cannot pass different arguments to the same job at
  different times, and the spec names one job, `dev.coordinator.overnight`.
- **The reach**: The job needs no state file and no second program. The
  hour of the PT clock is the whole rule, and `launchctl print` shows both
  entries. Any other hour, such as a job that fires after a sleep, does
  nothing instead of guessing.
- **Verdict**: sound.

### 2. The dry run is the shift's mode, and the report is its one write

- **The decision**: `--dry-run` means the shift does no work. The start
  reads the board and writes nothing; the report writes the morning report
  file, which is the only file a dry night writes.
- **The gap**: The brief says the plist is for the start and report times
  and that a dry run writes only the report. The spec's T12 says the same
  thing: a dry run writes the report only.
- **The reach**: Nothing is armed, no receipt is written and no work is
  started, so a night on this job cannot touch the board, a merge right,
  the slot cap or a push rule. The report is a record of the night, not
  work.
- **Verdict**: sound.

### 3. A real shift refuses instead of pretending

- **The decision**: `overnight shift` without `--dry-run` at the start
  hour exits non-zero and says that the arm and tick parts (T4, T5) are
  not built yet.
- **The gap**: The job is installed in dry-run mode. If someone later
  removes the flag without the tick landing, the job must not claim to
  have run a shift.
- **The reach**: The refusal is loud and says what is missing, so the
  next part can turn the mode on with the work behind it.
- **Verdict**: sound.

### 4. The job is written by the installer and loaded by the operator

- **The decision**: The installer copies the plist into
  `~/Library/LaunchAgents` with the other coordinator jobs and prints the
  exact `launchctl bootstrap` line for the overnight job. It does not load
  the job itself.
- **The gap**: The installer already writes the plists and tells the
  operator to load the changed jobs. Loading a job that fires at 22:30 is
  the operator's call, not the installer's.
- **The reach**: The other jobs keep their current behaviour, and the
  overnight job is loaded with one line that the installer prints.
- **Verdict**: sound.

## Proof

1. **The job is installed and loaded.** `python3 install_coordinator.py
   install` wrote `~/Library/LaunchAgents/dev.coordinator.overnight.plist`
   and `~/.local/bin/overnight`, and
   `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/dev.coordinator.overnight.plist`
   loaded it. `launchctl print gui/$(id -u)/dev.coordinator.overnight`
   shows the program, the arguments `shift --dry-run`, both calendar
   entries (22:30 and 06:30) and the log path
   (`evidence/MO-223/launchctl-print.log`).
2. **The job runs.** `launchctl kickstart -p gui/$(id -u)/dev.coordinator.overnight`
   ran it: `runs = 2`, `last exit code = 0`, and the log holds the one
   line it printed at 14:09 PT, "outside the overnight window; nothing to
   do" (`evidence/MO-223/kickstart-run.log`).
3. **The start part reads and writes nothing.**
   `~/.local/bin/overnight shift --at start --dry-run` printed the board
   (120 tickets, 15 allowed repositories, 148 records) and exited 0
   (`evidence/MO-223/dry-run-start.log`). The `.overnight` folder held no
   receipt, no run file and no inbox entry afterwards.
4. **A dry run writes only the report.**
   `~/.local/bin/overnight shift --at report` wrote
   `~/Code/coordinator/.overnight/receipts/morning-2026-11-13.md` and
   nothing else: `run/`, `inbox/` and `staging/` were empty afterwards
   (`evidence/MO-223/dry-run-report.log`).
5. **Checks.** `python3 scripts/mac_ops_fast_check.py` and the full local
   check through `heavy` are recorded in the pull request body.

## The reviewer round

One in-session reviewer round read `git diff origin/main...HEAD` against
this ticket. Its findings and the probes for them are in
`evidence/MO-223/reviewer-fixes.log`.
