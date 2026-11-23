# Event inbox T5: wake metrics script

Part of the coordinator event inbox (design: `docs/coordinator-event-inbox-design.md`, PR #897). Shadow mode only: this ticket changes no behavior of the tick, the guard, t56 or any launchd job.

## Goal and why

Add the one script that prints the design's before and after table for any window: event volume, runs a day, the four run-outcome buckets, latency from source event time, lost events (including a reconciliation of GitHub's PR list against `pr_opened` rows) and duplicate rate. It is read-only. It makes the baseline in the doc reproducible and is the instrument for the shadow week.

## Context

- Design: section 5 (the table and the four buckets), section 2 (baseline numbers to reproduce).
- Inputs: the launcher log (`~/Library/Logs/coordinator/tick.log`, one `exit=` line per run), the tick summaries (`~/Code/coordinator/loop/ticks.log`), the journal, and `inbox.db`.
- `evidence/event-inbox-design/` holds the scripts and outputs it must agree with.

## Scope and non-goals

In:

- `scripts/coord_wake_metrics.py` (new): flags `--journal`, `--launcher-log`, `--ticks-log`, `--inbox-dir` (all default to the real paths), `--since`, `--json`. Counts: `runs`, `failed` (a `pi exited` line with `402`), `noop`, `alerts`, `runs_per_day`, and the four buckets.
- `evidence/event-inbox-design/tickets/fixtures/` (new, excluded from the line count): `journal-sample.jsonl` and `launcher-sample.log` with 6 runs, 2 of them `Insufficient Balance` failures, 3 `NOOP` and 1 with an alert line.
- `runs.md` also pastes one read-only run on the real logs and compares it with the doc: 88 launcher runs in about 52 hours, 34 failed, 41 NOOP, 13 alert lines; 53% of the 106 count-format summaries acted on nothing.
- `evidence/MO-<issue#>/check-proof.md`, `evidence/MO-<issue#>/runs.md`.

Out: Any write to a log, the journal or `inbox.db`, a model call, any job, a change to the tick. Also out: any plist or job load, any model call, any send, `coordinator/pi/bin/coord-tick`, `coordinator/pi/extensions/coordinator.ts`, the live session t56, the live queue, the real journal and `~/.coordinator`.

## Design fit

Requires: T1's table layout (for the inbox-side counts).
Provides: The wake, latency and lost-event numbers the cutover decision needs.

## Blocked by

T1 (replace with the issue number once filed).

## Acceptance and proof

1. `python3 scripts/mac_ops_fast_check.py --proof evidence/MO-<issue#>/check-proof.md` passes on the final head.
2. runs.md: the proof command pasted red on origin/main (with the blockers merged) and green on the head, and the `inbox` eval of `coordinator/overnight/selftest.py` named as the case that fails on origin/main and passes on the branch.
3. The proof:

```text
Proof command:
HOME=/nonexistent python3 scripts/coord_wake_metrics.py --journal evidence/event-inbox-design/tickets/fixtures/journal-sample.jsonl --launcher-log evidence/event-inbox-design/tickets/fixtures/launcher-sample.log --inbox-dir "$(mktemp -d)" --json | python3 -c "import json,sys;d=json.load(sys.stdin);assert (d['runs'],d['failed'],d['noop'],d['alerts'])==(6,2,3,1),d"
Expected red signature: can't open file
Expected on main: can't open file
Expected on the head: exit 0
```

4. `Builder check: PASS <full sha>` on its own line in the PR body.

## Must not cause

- A write anywhere.
- A path under the real HOME read when a flag names a fixture.
- A model call, a send, a job load, or a change to the tick, the guard or t56.
- No new plist under `coordinator/launchd` (the installer loads every plist there), no weakening of an existing test and no new test file.

## CI

No workflows and no GitHub Actions, ever. The local check is `scripts/mac_ops_fast_check.py`.

## Data/secrets and stop conditions

Never read or print `models.json` or any API key. Never run `coordq dispatch`, refill, `ticket start/close` or the lane. Use a temp `COORD_INBOX_DIR` and `COORD_JOURNAL_DIR` for every run. Stop and report if over 3 code files or about 150 code lines.

## Rollback

Revert the merge commit.

## Gate

Astra gate on the PR head. Loop-code hold applies; Shyam merges after PASS.

## Finish

Report the PR, the head and the check line.
