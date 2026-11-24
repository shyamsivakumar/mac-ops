# Event inbox T2: journal hook writes inbox rows

Part of the coordinator event inbox (design: `docs/coordinator-event-inbox-design.md`, PR #897). Shadow mode only: this ticket changes no behavior of the tick, the guard, t56 or any launchd job.

## Goal and why

Make `journal.emit` write an inbox row for each wake-class and batch-class journal event, after the journal line is written. The producers (lane, gatekeep, alarms, coordq) do not change. A failed enqueue prints one line to stderr and the journal line still stands, as a failed journal write does today.

## Context

- Design: section 3.3 (journal events row and its writer), 3.2 (dedupe keys, `alarm:<name>:<generation>`).
- `coordinator/bin/journal.py` `emit` (lines 110 to 128) writes one line under `flock`; it is called by `coordq`, `gatekeep`, `lane_driver.py` (line 445, 743) and `alarms`.
- The 23 Nov journal has 475 `gate_queued`, 375 `alarm_raised`, 310 `gate_verdict`, 299 merges; `factory-watchdog` alone has 73 raise lines in 2 episodes, so the alarm key must carry a generation.

## Scope and non-goals

In:

- `coordinator/bin/inbox.py`: `from_journal(conn, row) -> dict | None` mapping `gate_queued` -> `gate_queued`, `gate_verdict` -> `gate_verdict`, `merged` and `merged_outside_lane` -> `pr_merged`, `alarm_raised` -> `alarm`, `round_cap`, `merge_held`, `close_failed`, `launch_failed`, `recut` -> the same kind. Key `<kind>:<repo>#<pr or ticket>:<head or empty>`; for `alarm` the key is `alarm:<name>:<generation>`, where the generation is kept in `meta` and incremented by an `alarm_withdrawn` line. Any other journal event returns `None`. `source` is `journal` and `ts` is the journal line's `ts`.
- `coordinator/bin/journal.py`: after the line is written, call `inbox.enqueue` for a mapped event. Setting `COORD_INBOX_HOOK`, default `on`; `off` writes no rows. A `sqlite3.Error` or `ImportError` prints one line to stderr and returns.
- `coordinator/overnight/selftest.py`: extend the `inbox` eval: switch off writes zero rows and the same journal bytes; an unwritable `COORD_INBOX_DIR` still writes the journal line; an event outside the map writes no row.
- `evidence/MO-<issue#>/check-proof.md`, `evidence/MO-<issue#>/runs.md`.

Out: Replay of old journal lines (T4), any poll, any change to `lane_driver.py`, `coordq` or gatekeep, `coord-tick`, `coordinator.ts`. Also out: any plist or job load, any model call, any send, `coordinator/pi/bin/coord-tick`, `coordinator/pi/extensions/coordinator.ts`, the live session t56, the live queue, the real journal and `~/.coordinator`.

## Design fit

Requires: T1's `enqueue`, `connect` and `meta`.
Provides: Live rows for journal events once the installer next copies `journal.py` and `inbox.py`.

## Blocked by

T1 (replace with the issue number once filed).

## Acceptance and proof

1. `python3 scripts/mac_ops_fast_check.py --proof evidence/MO-<issue#>/check-proof.md` passes on the final head.
2. runs.md: the proof command pasted red on origin/main (with the blockers merged) and green on the head, and the `inbox` eval of `coordinator/overnight/selftest.py` named as the case that fails on origin/main and passes on the branch.
3. The proof:

```text
Proof command:
HOME=/nonexistent python3 -c "import os,sys,tempfile;os.environ.update(COORD_JOURNAL_DIR=tempfile.mkdtemp(),COORD_INBOX_DIR=tempfile.mkdtemp());sys.path.insert(0,'coordinator/bin');import journal,inbox;[journal.emit('gate_verdict','lane',repo='o/r',pr=7,head='a'*40,verdict='PASS') for _ in (0,0)];journal.emit('alarm_raised','alarms',alarm='x-1');journal.emit('alarm_withdrawn','alarms',alarm='x-1');journal.emit('alarm_raised','alarms',alarm='x-1');c=inbox.counts();assert c['pending']==3,('hook',c)"
Expected red signature: AssertionError: ('hook',
Expected on main: AssertionError
Expected on the head: exit 0
```

4. `Builder check: PASS <full sha>` on its own line in the PR body.

## Must not cause

- A journal line lost, reordered or delayed by a failing inbox.
- A row for an event that is not in the map.
- Any change to what `coordq`, gatekeep, the lane or alarms write to the journal.
- A model call, a send, a job load, or a change to the tick, the guard or t56.
- No new plist under `coordinator/launchd` (the installer loads every plist there), no weakening of an existing test and no new test file.

## CI

No workflows and no GitHub Actions, ever. The local check is `scripts/mac_ops_fast_check.py`.

## Data/secrets and stop conditions

Never read or print `models.json` or any API key. Never run `coordq dispatch`, refill, `ticket start/close` or the lane. Use a temp `COORD_INBOX_DIR` and `COORD_JOURNAL_DIR` for every run. Stop and report if over 3 code files or about 150 code lines.

## Rollback

Set `COORD_INBOX_HOOK=off` for an immediate stop, or revert the merge commit and run the installer.

## Gate

Astra gate on the PR head. Loop-code hold applies; Shyam merges after PASS.

## Finish

Report the PR, the head and the check line.
