# MO-240 decisions: the shift runs 24x7 and the pi tick is retired

Refs #246. Type: standard change. Spec: overnight runner spec revision 3
(`~/Code/coordinator/specs/overnight-runner-spec.md`, Nov 13, 2026).

## What Shyam asked for

"don't use the tick then. just run the shift 24x7" (Nov 13, 2026). The pi
tick was the headless pi run that followed `loop/tick.md` every 30 minutes.
It is the piece that times out, so it never queued gates and never returned
a failed gate's findings, and it duplicated work the launchd jobs already
do. The shift should be the one loop that works the board, and it should
run all day, not only between 22:30 and 06:00.

## The decisions

### 1. The shift's job fires on a fixed interval, every day

`coordinator/launchd/dev.coordinator.overnight.plist` now carries
`StartInterval: 1800` and no `StartCalendarInterval`. One cycle every 30
minutes, at any hour of any day.

Why 1800 seconds: it is the cadence the retired tick had (spec revision 2,
"Tick cadence stays at 30 minutes"), so the shift replaces the tick's
cadence instead of adding a second one, and the board is worked at the rate
the coordinator is used to.

The interval lives in the plist and nowhere else. The command does not
carry a clock any more, so there is no second place that can disagree.

### 2. The shift has no parts of the night

`overnight shift` no longer decides which part of the night it is. The
night windows (`START_WINDOW`, `REPORT_WINDOW`, `shift_phase`) and the
`--at start` / `--at report` options are gone. Every run is one cycle.

The morning report is on demand now (`overnight report`), which is spec
revision 3, point 4, so the job no longer writes it and no calendar entry
remains for it.

### 3. A cycle is the policy, the board read and the cycle's record

A cycle reads the policy snapshot (`run/policy.json`, the T4 contract that
landed on main in MO-211), reads the board, orders it and writes the
cycle's line to `run/shift-log.md`. It writes no list file: the board is
the list, and the board's items stay in intake order because the shift
never writes to the board.

`run/STOP` still stops the shift at the next cycle, and it wins over
every other rule. A cycle that finds no policy snapshot refuses to work
(a dry run reads the board only and says so).

The shift is never armed: `run/armed` does not gate it, and there is no
night deadline.

### 4. The shift still does no work in this part

The plist runs `overnight shift --dry-run`, and a shift without
`--dry-run` still refuses with "the shift's board work is not built yet
(spec part T5)". The work part (T5) is its own ticket, and this ticket
changes only the schedule and the retirement of the tick. Nothing here
starts a ticket, so nothing here can start a ticket the ticket CLI would
refuse.

### 5. The tick job is retired in the repository and in the installer

The plist `coordinator/launchd/dev.coordinator.tick.plist` is deleted, so
the installer can no longer produce or install it: the installer renders
the plists from the folder, and the folder no longer holds a tick.

`install_coordinator.py` gained `RETIRED_JOBS = ("dev.coordinator.tick",)`
and `retire_jobs()`. When the installer runs against the real home and
finds the installed tick plist, it unloads the running job
(`launchctl bootout gui/<uid>/dev.coordinator.tick`), removes the plist,
and says what it did. A refusal is reported, never hidden.

The retirement is deliberately inert for a temporary home: `retire_jobs()`
only unloads a job for the real home, so a proof or a test that runs the
installer against a temporary home never touches the running jobs of the
machine. That is what makes the proof below safe.

`install_coordinator.py status` now reports `retired_jobs` and
`retired_leftovers`, so a leftover is visible before the install runs.

### 6. The tick's prompt is no longer the runbook for board work

`loop/tick.md` and the tick prompt are not what the coordinator follows
any more: the shift's own runbook is `coordinator/overnight/README.md`,
and that file now says so in the place where the runbook is described. The
README of the repository was corrected too, because it still described a
tick job that runs every 30 minutes.

The launcher `coordinator/pi/bin/coord-tick` and the guard extension's
wake prompt were left alone: the coordinator scoped this change to the
launchd folder, the installer and the overnight module. Nothing runs the
launcher any more, because no job points at it.

### 7. Merging origin/main

The first head could not be merged: `main` had moved on (MO-211, the T4
policy snapshot, and the attended first night). The branch now merges
`origin/main` (c0a41df) into it, so the push is a fast-forward and no
force push was needed. The conflicts are resolved by keeping both sides
of the contract:

- The T4 policy work stays: the cycle reads `run/policy.json`, prints the
  policy's lines, refuses to work when the snapshot names no repository,
  and `run/STOP` still stops the shift at the next cycle.
- The night phases go: `START_WINDOW`, `REPORT_WINDOW`, `shift_phase()`,
  the `--at start` / `--at report` options and the "outside the window"
  branch are gone, because the shift runs 24x7 and has no part of the
  night.
- The cycle keeps the board order: it reads the board, orders it and
  writes the cycle's line in the shift log. The morning report stays an
  on-demand command (`overnight report`), which the job does not run.

### 8. The retired-plist path list is built once

The gate's finding: the path of a retired job's plist was built in two
places, in the same way, for the dry run and for the status. One helper
now builds it: `retired_plist(label, home)` returns the path, and
`retired_plists(home)` returns the paths that are still there. The dry
run's `would_retire` and the status's `retired_leftovers` both come from
that one list, and `retire_jobs()` takes its path from the same helper.

(The helper was lost once: the merge onto `origin/main` took the file that
had no conflict, which was the version without it. The gate caught it, and
it is back in the head this body describes.)

### 9. The shift reads the policy snapshot's repository list

The gate's major finding: the cycle read the policy snapshot, printed its
lines, and then handed the work to `cmd_order` without the snapshot's list.
`cmd_order` fell back to the board config's list, so the T4 contract was
not enforced: the shift said "shift cycle under policy.json" and then read
every repository in the config.

`cmd_order` now takes the list the same way `cmd_intake` takes it on main:
an `allowed` override in the namespace. When the override is there, the
order reads the pull requests of those repositories only, and the filter
drops everything outside the list. The board config still holds the key of
each repository, so the blocker check reads the same keys as before.

A cycle without a snapshot is a dry run that reads the whole board and
says so, which is what it did before.

The proof (a scratch root with a snapshot that allows one repository):

```
$ cat <scratch>/run/policy.json
{"allow": ["shyamsivakumar/mac-ops"], "slot_cap": 6, "stall_cap": 3,
 "retry_cap": 2, "verify_level": "standard", ...}

$ python3 coordinator/overnight/overnight shift --dry-run --root <scratch> --deadline 300
overnight: 2026-11-13 18:32 PST shift cycle under <scratch>/run/policy.json
Allow list: 1 repositories (shyamsivakumar/mac-ops)
Slot cap: 6 (read only, from the coordq config; never raised)
Stall cap: 3 cycles with no new work
Retry cap: 2 fix tries per item, then it is parked
Verify level: standard
overnight: 2026-11-13 18:32 PST shift cycle (dry run, read only)
Overnight order - dry run (read only)
Board: 91 tickets
Allowed repositories: 1
Dropped by the filter: 81
Planned items: 10

Ready tickets already split into 5-minute parts (9)
  1. shyamsivakumar/mac-ops#181 MO-213 ... - already a 5-minute part
  ...
Summary line written to <scratch>/run/shift-log.md
  planned 10 items | shyamsivakumar/mac-ops 10 (failing 0, gate-pass 0, split 9, unsplit 1)
```

One repository in the list, one repository read, everything else dropped by
the filter. The same run without a snapshot reads the whole board (94
tickets, 15 repositories), so the difference is the snapshot's list and
nothing else.

### 10. Why the tick's launcher stays

The ticket retires the tick job and its runbook, not the launcher. The
launcher `coordinator/pi/bin/coord-tick` is the one part of the tick that
is not the job, it is the only way a person can still run a tick by hand,
and it lives in `coordinator/pi/`, which the coordinator's scope for this
ticket excluded. No plist points at it any more, so nothing runs it every
30 minutes. The repository README says this and why, so the file is not a
mystery.

## The proof

### The temporary home (no tick plist is produced or installed)

The repository installer, run against a temporary home:

```
1. the repository's launchd folder:
  dev.coordinator.dispatch.plist
  dev.coordinator.gatekeep.plist
  dev.coordinator.overnight.plist
  dev.coordinator.turncap.plist
  dev.coordinator.tick.plist present: False

2. the plists the installer wrote into the temporary home:
  dev.coordinator.dispatch.plist
  dev.coordinator.gatekeep.plist
  dev.coordinator.overnight.plist
  dev.coordinator.turncap.plist
  dev.coordinator.tick.plist installed: False

3. the installed overnight job:
  Label: dev.coordinator.overnight
  ProgramArguments: ['<home>/.local/bin/overnight', 'shift', '--dry-run']
  StartInterval: 1800
  StartCalendarInterval: None
  RunAtLoad: None
```

The retirement step in a temporary home that still held an installed tick
plist:

```
a temporary home that still holds an installed tick plist:
   <home>/Library/LaunchAgents/dev.coordinator.tick.plist exists: True
the installer retires it:
   Removed <home>/Library/LaunchAgents/dev.coordinator.tick.plist. The running job was left alone: this is not the real home.
   Removed the retired job's plist <home>/Library/LaunchAgents/dev.coordinator.tick.plist.
  tick plist still there: False
```

The live launchd jobs before and after the proof were identical, tick
included:

```
live launchd jobs before the proof:
  dev.coordinator.dispatch
  dev.coordinator.gatekeep
  dev.coordinator.overnight
  dev.coordinator.tick
  dev.coordinator.turncap
...
live launchd jobs unchanged: True
```

The live `dev.coordinator.tick` job is still loaded on this Mac on purpose.
Nothing was installed and nothing was unloaded here. The coordinator's
order is that MO-239 (#244) merges first, because the shift must be able
to send a failed gate's findings back to its builder before the tick stops
doing it. The uninstall happens at the first real install after both
merges.

`install_coordinator.py status` on the real home shows the leftover that
the next install will clear:

```
"retired_jobs": ["dev.coordinator.tick"],
"retired_leftovers": ["/Users/shyamsivakumar/Library/LaunchAgents/dev.coordinator.tick.plist"]
```

### The shift command by hand

```
$ python3 coordinator/overnight/overnight shift --dry-run --root <scratch> --deadline 300
overnight: <scratch>/run/policy.json does not exist; a dry run reads the board only
overnight: 2026-11-13 17:36 PST shift cycle (dry run, read only)
Overnight order - dry run (read only)
Board: 94 tickets
Allowed repositories: 15
Decisions log: /Users/shyamsivakumar/Code/coordinator/loop/decisions.md
Dropped by the filter: 5
Planned items: 86

Failing pull requests (5)
  1. shyamsivakumar/fantasy-football-toolkit#412 FFBT-9 ... - failing check: Vercel (FAILURE)
  ...
Pull requests with a gate PASS (0)
Ready tickets already split into 5-minute parts (17)
  6. shyamsivakumar/strategy-replay-workbench#891 SRW-1054 ... - already a 5-minute part
  ...
Not ready: the board stage is not todo (1)

Summary line written to <scratch>/run/shift-log.md
  planned 86 items | ...
No list file is written: the board is the list, and this run wrote one line of the shift log and nothing else.
```

The first line is the T4 contract: the scratch folder holds no policy
snapshot, so a dry run reads the board only and says so. A cycle with a
snapshot prints the snapshot's lines instead.

The cycle wrote one line to the shift log and nothing else, and the board's
items are in intake order: the shift wrote no list and changed nothing on
the board.

Per-item receipts (the spec's T5b) are not written by this part. A cycle
today writes the cycle's line in the shift log; the receipt per item and
per cycle lands with T5b (`mac-ops#181`, MO-213).

### The checks

```
$ ~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py
fast-check: passed; selected checks are not the full suite

$ ~/.local/bin/heavy python3 -m unittest discover -s tests -t .
Ran 192 tests in 3.708s
OK
```

## The tests

`tests/test_install_coordinator.py` had a `TestTickJob` class that asserted
the tick job was rendered, ran the tick launcher every thirty minutes and
logged into the tick log. That job is retired by this ticket, so those
assertions were replaced by `TestRetiredTickJob`, which asserts the
opposite: no tick plist is rendered, the repository holds no tick plist,
the tick is in the installer's retired set, the installer removes an
installed tick plist from a home that holds one, a home that holds none is
left alone, and the overnight job carries `StartInterval: 1800`, no
calendar interval and no `RunAtLoad`. No test was weakened to pass, and no
new test file was added.

## What is left

- The real install (which removes the installed tick plist and unloads the
  running job) happens after MO-239 (#244) merges. It is the installer's
  job now, so nothing else has to be run by hand.
- The launcher `coordinator/pi/bin/coord-tick`, the guard extension's wake
  prompt and `loop/tick.md` are still on disk. Nothing runs them. Removing
  them is a cleanup outside the scope this ticket was given.
- The shift's work parts (T4 arm, T5a the shift works the board, T5b
  receipts, T6 evidence, T7 redaction, T8 budgets and stall, T9 STOP,
  T10 parking lot) are their own tickets and are untouched here.
