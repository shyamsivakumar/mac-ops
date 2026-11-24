# Coordinator tick T0: skip the tick when no wake-class journal event is new

Stand-alone and optional; Shyam approved building it alongside the event inbox (design: `docs/coordinator-event-inbox-design.md`, section 2, "T0 replay", PR #897). Unlike T1 to T11 this ticket changes the live tick once the installer copies it, so it is not shadow-only: it makes no model call, sends nothing and loads no job, but it can make a scheduled tick exit without running. Merge and install wait for Shyam's own word.

## Goal and why

Today every 30-minute tick runs the selftest check, the model check and a model run, whether or not anything happened. Measured on 21 to 23 Nov: 88 launcher runs in about 52 hours (41 a day), of which 34 failed on `402 Insufficient Balance`, 41 replied NOOP and 13 sent an alert. The T0 replay (`evidence/event-inbox-design/t0_replay.py`) skips a tick when no wake-class journal event is newer than the last good tick, with a full tick forced every 2 hours: 78 of 109 clock ticks run (34.3 a day), 31 skipped (28%), about 15% fewer runs per hour than measured. A wake-class event waits a median of 16.2 minutes for its tick (p90 26.6), the same as today.

## Context

- `coordinator/pi/bin/coord-tick`: `main()` (lines 332 to 359) prints `tick_alarm()`, builds `child_env()` (100 to 111), takes the lock (313 to 329), then logs `tick_selftest()` (347), calls `model_available()` (348) and `run_tick()` (254 to 300). `log()` appends one line to `tick.log` (78 to 91). The `try/finally` at 346 to 359 releases the lock.
- Watchdog inputs (`coordinator/bin/tick_health.py`): `stale_log_alarm` alarms when `~/Library/Logs/coordinator/tick.log` is older than 65 minutes (a tick every 30 minutes needs a log line at least that often); `job_exit_alarms` alarms on a `dev.coordinator.tick` last exit other than 0 or 78; `drift_alarm` is independent. `tick_alarm()` runs at the top of `main()` before the lock, so it still runs on a skipped tick. `factory-watchdog` in the lane reads the same exit code.
- `coordinator/bin/hourly_selftest.py` `hourly()` keeps `last_run` and `passed` in `~/.local/state/mac-ops/overnight-selftest.json` and returns `not-due` when `last_run` is under 3600 s old; it is the only state `tick_selftest()` keeps.
- `coordinator/bin/journal.py` `emit` writes `events-YYYY-MM.jsonl` (UTC month) in `COORD_JOURNAL_DIR` or `~/.local/state/coordinator/journal`; lines carry `ts`, `event`, `actor` and a `data` object.
- Existing launcher tests are in `tests/test_install_coordinator.py` (`TestTickLauncher`, line 327, loads `coord-tick` by path).

## Scope and non-goals

In:

- `coordinator/pi/bin/coord-tick`: a `skip_reason(now)` check placed inside the existing `try/finally`, after the lock is taken and before `tick_selftest()`. `tick_alarm()` and the lock stay where they are. A skip releases the lock through the existing `finally` (a first draft that returned before the `try` leaked the lock, so the next call logged "another tick holds the lock").
- The mark: a JSON file `{"started": <epoch>, "ran": <epoch>}` at `COORD_TICK_MARK`, default `~/.local/state/mac-ops/coord-tick.mark` (beside the lock), written atomically (temp file and `os.replace`) only when `run_tick` returns 0. `started` is the time the tick began, before the selftest, so an event that lands while the run is in flight counts as new for the next tick. A failed tick (any nonzero code: pi error, 124 timeout, 75 model unavailable, the 402 case) leaves the mark as it was. A skipped tick never writes the mark, so the cap counts from the last real run.
- Wake-class set `WAKE_EVENTS`, overridable by `COORD_TICK_WAKE_EVENTS` (comma list), default `alarm_raised,round_cap,merge_held,close_failed,launch_failed,recut`: the design's variant B kinds, the same list the T0 replay used. It does not read T1's setting, so T0 has no dependency.
- Skip only when all hold: `COORD_TICK_PRECHECK` is not `off`; the mark parses; `0 <= now - started < cap`; and the journal scan proves no wake-class event after `started`. Anything else runs the tick. Never skip on doubt.
- The scan reads the month files from `started`'s UTC month to `now`'s UTC month in order (a boundary crossing reads both). A month file that does not exist has no events; any other read error runs the tick. It reads the last 1 MiB of a file; a file counts as clean only if it was read in full or the tail reached a line with `ts` at or before `started`, otherwise the scan is unproven and the tick runs. A line inside the window that does not parse runs the tick (one bad line does not crash the caller; it just stops the skip until it ages out of the window). A line with `data.via_tick` is ignored.
- Own writes: `child_env()` adds `COORD_TICK_RUN=1`, and `coordinator/bin/journal.py` `emit` adds `data["via_tick"] = true` when that variable is set. Journal lines written by the tick's own commands (`coordq`, `ticket`, the card writer) then carry the tag and do not wake the next tick. Events written later by the lane or gatekeep in response to what the tick did are untagged and do wake it, which is intended.
- A skip logs exactly one `skip` line through `log()`, for example `skip: no wake-class journal event since 14:02 EST; full tick due by 16:02 EST`, and returns 0. The log write is what keeps `tick.log` under the 65-minute limit, and the 0 keeps the job's last exit at 0, so no watchdog alarm fires on a skip. The skip does not call `tick_selftest()` and does not touch `overnight-selftest.json`.
- Settings: `COORD_TICK_PRECHECK` (default `on`; `off` runs every tick as today), `COORD_TICK_PRECHECK_CAP` (default `7200` seconds), `COORD_TICK_MARK`, `COORD_TICK_WAKE_EVENTS`.
- `tests/test_install_coordinator.py` (extend `TestTickLauncher`): month boundary (mark at 30 Nov 23:50 UTC; an event in the December file runs, an event in the November file after the mark runs, none skips), an unparsable line in the window runs, an unreadable journal directory runs, a mark from the future runs.
- `evidence/MO-<issue#>/check-proof.md`, `evidence/MO-<issue#>/runs.md`.

Out: any change to the tick prompt, `run_tick`, `model_available`, `deliver`, `alert_lines`, the launchd plist or its interval, `coordinator.ts` and the in-session idle timer, the guard, t56, T1 to T11's inbox files, the model, and any live run (the proof stands a fake pi in `run_tick`).

## What skipping loses, and how long it can take

The tick reads the whole board each time (`overnight board --json --action`). A skipped tick does not, so it misses anything the journal does not carry as a wake-class event:

- Board drift: a PR opened, held, draft or ungated, a new head, a merge, a gate verdict and a stage label change are journal events (`gate_queued`, `gate_verdict`, `merged`) or board state, but none is in the wake set, so they wait for the next full tick unless an alarm, `round_cap`, `merge_held`, `close_failed`, `launch_failed` or `recut` line arrives.
- Shyam's replies and approvals on GitHub (a review, a comment, the `merge:human-ok` label) and answers to cards in `decisions.json`. The journal does not record them.
- CI statuses on `main`, and builder threads that stall without a journal line.
- Housekeeping the model does each tick (settling dead runs, drift notes, the board-integrity pass).

Maximum delay: a wake-class journal event is handled at the next tick, as today (at most 30 minutes plus the run). A fact the journal does not carry waits for the forced full tick: 7,200 seconds after the last good tick started, and since ticks are 30 minutes apart and start with some jitter, at most 7,200 + 1,800 = 9,000 seconds (2.5 hours). That is the stated cost of T0.

`tick_selftest()` and its hourly schedule: a skipped tick does not call it and writes nothing, so `last_run` in `overnight-selftest.json` is unchanged. The next full tick finds `last_run` older than 3,600 s and runs the suite. The schedule cannot break, because it is a timestamp comparison with no counter; it only runs less often. A failing fixture suite (the `ALARM` card in `decisions.json`) is noticed up to 2.5 hours after it starts failing instead of up to 1.5, and `tick.log` shows fewer `overnight selftest:` lines.

## Design fit

Requires: nothing new (no inbox file).
Provides: most of the run-count saving the inbox replays to, with no new store. If the inbox cuts over (T12 unloads this tick), the precheck becomes dead code and T12 removes it or leaves it harmless.

## Blocked by

None.

Overlap with other tickets (merge order, not a block): T9 as written in this folder does not edit `coord-tick`, so there is no conflict with it. If a filed T9 imports or edits `coord-tick`, T0 changes only `main()` between `take_lock()` and `tick_selftest()`, `child_env()` (one added key) and new top-level names (`WAKE_EVENTS`, `mark_path`, `skip_reason`, `write_mark`); it leaves the signatures of `run_tick`, `model_available`, `deliver` and `alert_lines` alone, so T0 should merge first and T9 rebase. T2 also edits `coordinator/bin/journal.py` `emit` (a different block: after the write, versus the `data` tag before it), so whichever merges second rebases a small hunk.

## Acceptance and proof

1. `python3 scripts/mac_ops_fast_check.py --proof evidence/MO-<issue#>/check-proof.md` passes on the final head.
2. runs.md: the proof command pasted red on origin/main and green on the head, and the new `TestTickLauncher` cases run singly with a temp `COORD_JOURNAL_DIR`, red on origin/main and green on the head.
3. The proof (the fake pi is a stand-in for `run_tick`, so no pi, sandbox or model starts; it shows a first run with no mark, a skip with its log line, a wake event, the tick's own tagged write, a failed run that keeps the mark, a corrupt mark, the cap and the off switch):

```text
Proof command:
HOME=/nonexistent python3 -c "import os,sys,json,time,tempfile,importlib.util as u;from importlib.machinery import SourceFileLoader as L;d=tempfile.mkdtemp();os.environ.update(HOME=d,COORD_JOURNAL_DIR=d,COORD_TICK_LOG=d+'/t.log',COORD_TICK_LOCK=d+'/l',COORD_TICK_MARK=d+'/m');sys.path.insert(0,'coordinator/bin');import journal;s=L('ct','coordinator/pi/bin/coord-tick');m=u.module_from_spec(u.spec_from_loader('ct',s));s.exec_module(m);c=[];rc=[0];m.tick_alarm=lambda:'';m.tick_selftest=lambda:c.append('selftest') or 'PASS';m.model_available=lambda e:True;m.run_tick=lambda e,fd:c.append('pi') or rc[0];g=lambda:(c.clear(),m.main(),list(c))[2];ev=lambda n:journal.emit('alarm_raised','alarms',alarm=n);R=['selftest','pi'];assert g()==R,'no mark runs';assert g()==[] and 'skip' in open(d+'/t.log').read(),'skip';ev('x');assert g()==R,'event runs';os.environ['COORD_TICK_RUN']='1';ev('y');del os.environ['COORD_TICK_RUN'];assert g()==[],'own writes';rc[0]=1;ev('z');assert g()==R and g()==R,'failed run keeps the mark';rc[0]=0;g();open(d+'/m','w').write('junk');assert g()==R,'bad mark runs';assert g()==[],'skips again';json.dump({'started':time.time()-7300,'ran':time.time()-7300},open(d+'/m','w'));assert g()==R,'cap';assert g()==[];os.environ['COORD_TICK_PRECHECK']='off';assert g()==R,'off switch'"
Expected red signature: AssertionError: skip
Expected on main: AssertionError
Expected on the head: exit 0
```

4. `Builder check: PASS <full sha>` on its own line in the PR body.

## Must not cause

- A skip that raises a watchdog alarm: `tick.log` must get its line and the exit code must be 0.
- A skip on any doubt (a missing, corrupt or future mark, an unreadable journal, an unproven scan, the cap).
- A mark advanced by a failed tick or by a skip.
- The tick's own journal writes waking the next tick.
- A leaked lock on the skip path.
- A real tick, a job reload, an installer run or a change to the plist's 30-minute interval by the builder.
- No weakening of an existing test and no new test file.

## CI

No workflows and no GitHub Actions, ever. The local check is `scripts/mac_ops_fast_check.py`.

## Data/secrets and stop conditions

Never read or print `models.json` or any API key. Never run `coordq dispatch`, refill, `ticket start/close` or the lane. Use a temp `HOME`, `COORD_JOURNAL_DIR`, `COORD_TICK_LOG`, `COORD_TICK_LOCK` and `COORD_TICK_MARK` for every run, and never the live `tick.log`, mark or journal. Stop and report if over 3 code files or about 150 code lines (about 70 are expected in `coord-tick` and `journal.py`, the rest in the test).

## Rollback

Set `COORD_TICK_PRECHECK=off` in the plist environment for an immediate return to every-tick behavior, or revert the merge commit and run the installer. Delete nothing: the mark file is harmless and is ignored when the switch is off.

## Gate

Astra gate on the PR head. Loop-code hold applies; Shyam merges after PASS.

## Finish

Report the PR, the head and the check line.
