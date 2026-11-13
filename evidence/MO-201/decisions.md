# Decisions ledger — MO-201

Run: `ticket:shyamsivakumar/mac-ops#166:a1`

Ticket: https://github.com/shyamsivakumar/mac-ops/issues/166

Base: `origin/main` at `e2aa2e1` (Mirror every coordinator turn to the phone relay
(Refs #158) (#164)).

Authority: Shyam, 2026-11-12: "have the 5 minute ticker check everything on the
board and keep moving things along, especially the ones that need me, and
backlog and ready ones".

## Scope

Two values in the existing job, per the brief:

1. `coordinator/launchd/dev.coordinator.tick.plist`: `StartInterval` 1800 -> 300.
2. `coordinator/pi/bin/coord-tick`: the in-run kill 600 s -> 240 s.

Out of scope and untouched: the tick prompt, `loop/tick.md`, the guard, the
board-sweep rules, and every other launchd job.

## Sound

### The interval change is one integer in the existing job

**When:** MO-201 implementation, 2026-11-12 PT.

*`StartInterval` was the only scheduling value in the job. The job has no
`RunAtLoad`, keeps its own launcher lock, and keeps its own log path, so a
shorter interval changes when the tick starts and nothing else. The plist
comment above the dict said "every 30 minutes" and now says "every 5
minutes", so the file does not describe a schedule it no longer runs.*

**Gap:** the brief named "one plist value and the matching doc line"; the
comment line inside the same file describes that value and was updated with it.

**Reach:** `launchctl print gui/$(id -u)/dev.coordinator.tick` reports the
interval; every other key of the job is byte-identical.

**Verdict:** sound — one integer plus the sentence that names it.

**Confidence:** high — the rendered plist was parsed and the interval read
back as 300; the install suite asserts the same value.

**Owner:** `coordinator/launchd/dev.coordinator.tick.plist:16`

### The in-run kill drops below the interval

**When:** MO-201 implementation, 2026-11-12 PT.

*`COORD_TICK_TIMEOUT` defaulted to 600 s while the interval was 1800 s. With
a 300 s interval the old default could let a stuck run hold the lock across
the next scheduled tick, so the default is now 240 s: a run is killed before
the next interval arrives. The lock still excludes overlap, so the shorter
kill does not create a second tick; it only ends a stuck one earlier. The
environment knob is unchanged, so an operator can still raise it.*

**Gap:** the brief said "lower the in-run kill from 10 to 4 minutes so a slow
tick never overlaps the next one for long (the lock already stops overlap)";
the default constant and the docstring that names it are the whole change.

**Reach:** `TIMEOUT_S` is the only consumer of `COORD_TICK_TIMEOUT`; the kill
path (SIGTERM to the child process group, then SIGKILL) is unchanged and
still returns 124.

**Verdict:** sound — one default value and its two mentions.

**Confidence:** high — the kill path was exercised live with
`COORD_TICK_TIMEOUT=1` and logged `tick killed after 1s` with exit code 124;
the default was read back as 240 from the installed module.

**Owner:** `coordinator/pi/bin/coord-tick:42`

### The test that pins the interval moves with the value

**When:** MO-201 implementation, 2026-11-12 PT.

*`tests/test_install_coordinator.py` asserted `StartInterval == 1800` and the
test name and class docstring said "thirty minutes". The stated behavior
change is 300, so the assertion, the test name and the docstring were
changed to match. No assertion was removed, weakened or skipped; the test
still fails if the rendered job carries any other interval. This is the only
test file touched.*

**Gap:** the brief did not list the test line. Leaving it would have made the
suite red against the stated behavior change.

**Reach:** the whole `tests/test_install_coordinator.py` suite (34 tests) still
passes; the tick job class keeps every assertion it had.

**Verdict:** sound — the expectation tracks the stated behavior change.

**Confidence:** high — the suite fails if the interval reverts to 1800.

**Owner:** `tests/test_install_coordinator.py:226`

## Proof

```text
python3 scripts/mac_ops_fast_check.py          -> fast-check: passed
heavy python3 scripts/mac_ops_fast_check.py     -> fast-check: passed
heavy python3 -m unittest tests.test_install_coordinator -v
  Ran 34 tests in 0.664s
  OK
COORD_TICK_TIMEOUT=1 coord-tick                  -> exit 124, log "tick killed after 1s"
module default TIMEOUT_S                         -> 240
plistlib load of the rendered job                -> StartInterval 300
```

No live launchd job was reloaded by this build; the install and reload run
after the merge.

## In-session review

One Opus review round against `git diff origin/main...HEAD`. The verdict and
the reviewed head SHA are in the PR body and the final report.

## Rollback

Revert this change and reinstall: `StartInterval` returns to 1800 and the
in-run kill returns to 600 s. Reload the job with `launchctl bootout` and
`launchctl bootstrap`.
