# MO-199 — Coordinator tick on launchd as headless Sonnet

- Ticket: https://github.com/shyamsivakumar/mac-ops/issues/161 (Refs #161).
- Spec: https://github.com/shyamsivakumar/mac-ops/issues/160.
- Run id: `ticket:shyamsivakumar/mac-ops#161:a1`.
- Executed 2026-11-12 PT. Base: `origin/main`, merge base `2af2cb86caaf426661b46136ee80529dd1518535`.
- Authority: the ticket and the spec it names. Shyam 2026-11-12: "lets do b".

## What landed

- `coordinator/pi/bin/coord-tick`: one tick per run. A fresh headless
  `pi -p --no-session --model pi-claude-cli/claude-sonnet-5-5` in the
  coordinator sandbox, with `PI_CODING_AGENT_DIR=~/.pi/agent-coordinator`,
  cwd `~/Code/coordinator`. A lock keeps two ticks apart, a ten-minute cap
  kills a long run, and the `ALERT:` lines of the reply go to the live pi
  coordinator terminal with `hc send`. A `NOOP` reply sends nothing.
- `coordinator/launchd/dev.coordinator.tick.plist`: `StartInterval 1800`,
  logs into `~/Library/Logs/coordinator/tick.log`.
- `coordinator/pi/bin/coord-pi`: `export COORD_WAKE=0`.
- `install_coordinator.py`: `coord-tick` joins the pi launchers
  (`PI_BIN_FILES`). The plist installs by itself: the installer globs
  `coordinator/launchd/*.plist`.
- `tests/test_install_coordinator.py`: the tick job's shape, the launcher
  mapping, the alert parsing, the prompt override and the lock.

Not touched: `coordinator.ts`, the sandbox profile, `loop/tick.md`,
gatekeep, dispatch, and every existing check. No existing test or check was
weakened.

## Decisions ledger

Every call the ticket left to the builder, and what it costs.

### 1. The lock lives at `~/.local/state/mac-ops/coord-tick.lock`, not in `$TMPDIR`

- **When**: commit `0076562`.
- **The decision**: One fixed path per user, whatever the caller is. The
  ticket suggested "flock or mkdir lock in `$TMPDIR`". A `$TMPDIR` lock only
  works when every caller shares one `$TMPDIR`. A shell on this Mac gets
  `/var/folders/d3/.../T`, and the launchd job gets none at all, so a
  `$TMPDIR` lock would put the scheduled tick and a manual tick on two
  different files, and the two would happily run at the same time. The
  launcher now uses one path (`COORD_TICK_LOCK` overrides it, for tests).
- **The gap**: The ticket named a lock mechanism, not where the lock file
  must live, and did not notice that launchd and a shell disagree about
  `$TMPDIR`.
- **The reach**: Every future caller of `coord-tick` (a second launchd job, a
  manual run, a test) has to use the same lock path, or the "no two ticks at
  once" promise silently breaks.
- **Verdict**: sound. The alternative (a `$TMPDIR` lock) fails the ticket's
  own "must not cause: no second tick at the same time".
- **Confidence**: high.

### 2. The lock is an `flock` on a file, not a `mkdir` lock

- **When**: commit `0076562`.
- **The decision**: The launcher opens the lock file with `O_CREAT` and
  `O_NOFOLLOW` and takes an exclusive `flock` on it. A `mkdir` lock leaves a
  stale directory behind when a run is killed, and the next run would then
  skip for ever. `flock` is released by the kernel when the process dies, so
  a killed tick leaves nothing behind.
- **The gap**: The ticket allowed either mechanism.
- **The reach**: A future tick launcher that uses a `mkdir` lock would
  reintroduce the stale-lock failure.
- **Verdict**: sound.
- **Confidence**: high.

### 3. A run that finds the lock held exits 0 and logs one line

- **When**: commit `0076562`.
- **The decision**: "skipped: another tick holds the lock" and exit code 0. A
  scheduled job that exits non-zero looks like a failure in the log and in
  any monitor watching it, and skipping is the normal case, not a fault. The
  line in the tick log is the signal.
- **The gap**: The ticket says "the second exits at the lock with a log
  line" and does not say with which code.
- **The reach**: Any future caller that treats a non-zero exit as "the tick
  failed" would be misled by this choice, and the reverse choice would make
  every overlapping minute look like an error.
- **Verdict**: sound.
- **Confidence**: medium.

### 4. The launchd job has no `RunAtLoad`

- **When**: commit `0076562`.
- **The decision**: The job runs every 1800 seconds and does not run once at
  load. A tick costs a model call, so the first one lands one interval after
  the job loads rather than at every boot and every reinstall. The other
  coordinator jobs (`gatekeep`, `dispatch`) do run at load, but they are
  mechanical and free.
- **The gap**: The ticket fixed the interval and the log path and said
  nothing about `RunAtLoad`.
- **The reach**: After a reboot the board waits up to 30 minutes for the
  first tick. If Shyam wants a tick right after every boot, the fix is one
  line in the plist.
- **Verdict**: needs-user. Recommended provisional call: keep it off.
  Reversal: add `<key>RunAtLoad</key><true/>` to the plist and reinstall.
- **Confidence**: medium.

### 5. The launcher is a Python script, not a shell script

- **When**: commit `0076562`.
- **The decision**: `coord-tick` is Python 3, like `coord-ask` next to it.
  The job needs an exclusive lock, a kill of the whole process group after
  ten minutes, JSON parsing of `hc ls` and a check that the provider still
  offers the model. Shell would mean `flock(1)`, which macOS does not ship,
  or a homegrown lock.
- **The gap**: The ticket said "a `coord-tick` launcher" and named the
  existing `coord-pi` shell launcher as the pattern, but `coord-ask` is
  Python and the work needs Python.
- **The reach**: The next launcher in this set will probably be Python too.
- **Verdict**: sound.
- **Confidence**: high.

### 6. The tick runs with `--no-skills`, and the launcher itself exports `COORD_WAKE=0`

- **When**: commit `0076562`.
- **The decision**: The tick needs `coordq`, `ticket` and `t3mcp` from the
  shell, not skills, so the skill catalogue stays off and the tick stays
  cheap. The launcher also sets `COORD_WAKE=0` for its own child: a
  one-shot headless run has nothing to wake, and the timer would keep the
  process alive.
- **The gap**: The ticket fixed the command line without these flags and did
  not mention the wake timer inside the tick process.
- **The reach**: If a future tick needs a skill, it has to load it
  explicitly, and a tick that hangs on a wake timer would hit the ten-minute
  cap for the wrong reason.
- **Verdict**: sound.
- **Confidence**: medium.

### 7. The launcher checks the model before the run and stops with `WAITING`

- **When**: commit `0076562`.
- **The decision**: `pi --list-models` runs first. If the model is not there,
  the launcher logs "WAITING: `<model>` is not available on the provider" and
  exits 75 without spending a tick. If the check itself cannot run, the tick
  runs anyway and reports its own failure.
- **The gap**: The ticket says "If Sonnet is not available on pi-claude-cli,
  stop with WAITING" but not how to notice.
- **The reach**: Every new model the tick uses needs the same check, or the
  launcher has to grow a list.
- **Verdict**: sound.
- **Confidence**: medium.

### 8. The alert lookup is a copy of the one in `coord-ask`

- **When**: commit `0076562`.
- **The decision**: The launcher looks for a live terminal with agent `pi`
  and cwd `~/Code/coordinator`, preferring the one in the "Pi - Coordinator"
  tab, the same rule `coord-ask` uses. It is copied, not imported, because
  `coord-ask` is a script and not a module. Only that terminal is ever
  written to.
- **The gap**: The ticket said to reuse the lookup without saying where the
  shared code should live.
- **The reach**: If the coordinator terminal moves, both copies have to
  change. A shared module would be the fix, at the cost of touching
  `coord-ask` too, which this ticket does not cover.
- **Verdict**: sound, with a known duplication.
- **Confidence**: medium.

### 9. Four environment knobs on the launcher

- **When**: commit `0076562`.
- **The decision**: `COORD_TICK_PROMPT_OVERRIDE` (the ticket's own
  acceptance hook), plus `COORD_TICK_LOG`, `COORD_TICK_LOCK` and
  `COORD_TICK_TIMEOUT` for the same reason: the proofs and the tests need to
  point the launcher at scratch paths and at a short cap.
- **The gap**: The ticket named only the prompt override.
- **The reach**: These are the launcher's public surface. A knob nobody uses
  is dead weight; they are documented in the script header.
- **Verdict**: sound.
- **Confidence**: medium.

### 10. The tick log is both the launchd log and the launcher's own log

- **When**: commit `0076562`.
- **The decision**: The plist points `StandardOutPath` and
  `StandardErrorPath` at `~/Library/Logs/coordinator/tick.log`, and the
  launcher appends its own summary lines to the same file. The launchd
  output holds the pi reply, the launcher's lines hold the run summary, so
  one file shows both.
- **The gap**: The ticket fixed the log path for the job and asked for a
  tick log line, without saying whether they are one file.
- **The reach**: A future reader of `tick.log` has to know that the file
  mixes pi output and launcher lines.
- **Verdict**: sound.
- **Confidence**: high.

## Proof

Every acceptance item was run against the installed launcher
(`~/.local/bin/coord-tick`, installed with `./install.sh coordinator`).

1. **NOOP run.** `COORD_TICK_PROMPT_OVERRIDE="Reply exactly NOOP. Use no
   tools." ~/.local/bin/coord-tick` → exit 0, stdout `NOOP`, and
   `~/Library/Logs/coordinator/tick.log` gained
   `2026-11-12 18:23 PST | tick | exit=0 reply=NOOP`. The coordinator session
   folder held 7 files before and 7 files after, so no session file was
   written and the newest session that `coord-ask`, the phone relay and the
   Herdr panel read is still the coordinator's own.
2. **ALERT run.** `COORD_TICK_PROMPT_OVERRIDE="Reply exactly: ALERT: tick
   test"` → the launcher logged `alert sent to t56: ALERT: tick test`, and
   `hc read t56` showed `Steering: Tick alert: ALERT: tick test` in the
   coordinator terminal. The message went to the pi coordinator terminal and
   nowhere else.
3. **Overlap.** One run started with a 25 second prompt, a second run
   started five seconds later: the second exited in 0.05 s with
   `skipped: another tick holds the lock` in the tick log and exit code 0.
4. **Safety.** `COORD_TICK_PROMPT_OVERRIDE="Use the bash tool to run: touch
   ~/Code/mac-ops/.probe . ..."` → the reply was `The guard blocked it:
   touch ~/Code/mac-ops/.probe was denied because writes into a repo aren't
   allowed from the coordinator, so nothing was created`, and
   `ls -l ~/Code/mac-ops/.probe` reported no such file. The coordinator
   sandbox and the guard both hold.
5. **The job.** `launchctl bootstrap gui/$(id -u)
   ~/Library/LaunchAgents/dev.coordinator.tick.plist` and
   `launchctl print gui/$(id -u)/dev.coordinator.tick` →
   `run interval = 1800 seconds`, `program =
   /Users/shyamsivakumar/.local/bin/coord-tick`, `stdout path =
   /Users/shyamsivakumar/Library/Logs/coordinator/tick.log`, `state = not
   running` (no `RunAtLoad`, so no tick fires at load).
6. **The ten-minute cap.** `COORD_TICK_TIMEOUT=8` with a prompt that sleeps
   120 seconds → `tick killed after 8s`, exit code 124, and no stray
   `sleep 120` process left behind. The signal goes to the whole process
   group, so the child dies with it.
7. **Checks.** `python3 scripts/mac_ops_fast_check.py` → `Ran 31 tests ... OK`,
   `fast-check: passed; selected checks are not the full suite`. The same
   command through heavy (`~/.local/bin/heavy python3
   scripts/mac_ops_fast_check.py`) → same result.

## Live state on this Mac

The installer wrote `~/.local/bin/coord-tick` and
`~/Library/LaunchAgents/dev.coordinator.tick.plist`, and the job is loaded
(`dev.coordinator.tick`, interval 1800). The coordinator's own session was
started before this change, so it still has its 30 minute wake timer on:
**Shyam must restart `coord-pi` for `COORD_WAKE=0` to apply.** Until then
both tick sources exist, and the two can overlap once, because the launchd
tick's lock is not the in-session tick's lock.

## Rollback

```sh
launchctl bootout gui/$(id -u)/dev.coordinator.tick   # stop the job
cd <mac-ops checkout> && ./install.sh coordinator      # reinstall without the tick
```

To bring the in-session 30 minute wake back, remove `export COORD_WAKE=0`
from `coordinator/pi/bin/coord-pi` and reinstall, or run `/wake on` in the
coordinator session.

No rollback has been executed. The PR merge and the Opus gate are
coordinator-owned.
