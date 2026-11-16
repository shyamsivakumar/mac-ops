# MO-1006 delivery

Refs #345. Run ticket:shyamsivakumar/mac-ops#345:a1.

Fresh base: 8d6c70d4146cf857a59d0081159e784773837635. Fetched and rebased
on origin/main. Native blocked-by relationship to closed #344 was verified in
the initial turn; watch-lanes is present at the base.

The continuation supersedes scope-stop.md. Read the external lane.md and
notes.md from /Users/shyamsivakumar/Code/coordinator without modifying them.

Decisions: foreground continuous mode is default, with --once retained for
existing callers. Run identity comes from activeRunId and the matching latest
recentRuns entry, never thread creation time. Running threads without a known
start time stay unknown. Rate-limit and traceback events are read from explicit
logs or the queue dispatch.log default. Only the state file is written at runtime;
its parent must exist. The lifetime lock prevents a second watcher sharing state.
No dispatch, mutation, labels, PR actions or lane scheduler are in the watcher.

Installer source contract already maps coordinator/bin/coord-watch to
~/.local/bin/coord-watch at mode 0755 via BIN_FILES and plan(). No redundant
mapping edit was made. The gate fix now executes the real installer in a
temporary HOME with host discovery/activation boundaries replaced by inert
fakes. No live installation or package execution was performed.

Verification command (required agent check):

    timeout 300 python3 scripts/mac_ops_fast_check.py

Device, handset, live-service and owner testing are waived by Shyam's
2026-11-14 instruction, not failed. No new unit tests were created. The gate
fix supplies the isolated command acceptance replay and actual temporary-HOME
installation receipts described below.
The fast check covers changed Python syntax and existing selected checks,
including the HeavyQueue model, not end-to-end runtime acceptance.

Deslop review used standard-library facilities and existing installer mapping;
no dependencies or cleanup installs. no-comments diff review: only the CLI
module docstring changed; it describes the command contract. No added code
comments or suppressions. Documentation is updated in docs/coord-watch.md,
already linked from README.md. Proof runtime writes are isolated to temporary
HOME directories; no other repository or live runtime files are modified.

Limitations: persistence precedes printing, so a crash in that window can lose
an event; state loss can repeat events. Unread tails of rotated-away files are
not recovered. Identical truncate/regrow boundaries cannot be detected. State
history exceeding 8 MiB fails visibly and requires operator intervention.
Signal shutdown during collection can take up to the 120-second shared deadline.
No live activation, merge or next-ticket start. Provides watch-complete remains
subject to coordinator review and verification on merge.

## Gate fix: missing isolated acceptance receipts

The major finding on head 853a6cc57545e97013edf70f2ec6dffd0f520c5e is
addressed by evidence/MO-1006/replay.py and its captured replay.out. Reproduce:

    timeout 300 env PYTHONDONTWRITEBYTECODE=1 python3 evidence/MO-1006/replay.py

The script runs the actual executable with --once, --fake-input and explicit
state/log paths in a fresh temporary HOME. Every cycle is a new process.
Fake now/start timestamps prove silence below and exactly at 20 minutes,
one event after 20 minutes, silence after restart, and a new event for a new
run identity. Partial thread sources, waiting status and unknown starts are
silent. Synthetic logs prove rate-limit and traceback events, partial-line
completion, restart dedup, inode replacement rotation, and copy truncation.
Assertions compare exact event lists and require one BOARD line per cycle.
Each invocation snapshots temporary-HOME files and verifies only its state
file changes. A synthetic private marker must be absent from command stdout,
stderr and state. No credentials or real secret-bearing logs are read.

Installation calls install_coordinator.install with dry_run=False and the
actual checkout, temporary home and coordinator paths. The real plan,
changes, writes, backup and receipt paths execute. Only git_toplevel,
retire_jobs, manual_monitors and reload_jobs are replaced with inert fake
boundaries, preventing host discovery/activation. All subprocesses during
installation are forbidden. The script asserts the unique plan mapping,
source-byte equality, executable 0755 mode, installation receipt entry, and
then executes the installed ~/.local/bin/coord-watch for deduplication and a
new event. This proves file installation, not launchd activation, which remains
out of scope. All command subprocesses have 15-second timeouts.

Observed result: replay exit 0; every listed case PASS. Device, handset and
live-service cases are WAIVED, not failed. No production process started.
This is a proof-only gate fix; runtime and installer source are unchanged.

## Gate fix: identical-line copy truncation

The major finding at e3a3917530c7d48252d468cd560bf98254f867ac is
resolved by persisting logOffsets[path].generation and including nonzero
generations in event identities. Detected shrinkage or a changed saved boundary
increments it before resetting the offset. File replacement also increments
it. Legacy state starts at zero and retains existing event identity formatting,
so upgrading does not repeat already-seen alarms. Normal append/restart keeps
the generation unchanged.

Before the fix, the extended real-command replay failed with
`identical-line copy truncate: unexpected events []`. After the fix, the same
case emits exactly one rate-limit event, verifies the inode is unchanged and
the generation increments once, then restarts with no duplicate event. The
replay also verifies a truncate/regrow boundary mismatch increments generation
and emits the repeated prefix alarm once; another restart stays silent. A
legacy-state case removes the generation field and verifies silent migration
to zero. Existing threshold, rotation, installed-executable and privacy cases
continue to pass. Reproduce with the replay command above; replay.out captures
the completed result.

Device, handset and live-service cases remain WAIVED, not failed. No live
runtime changes or activation occurred. The inherent identical truncate/regrow
boundary detection limit remains documented. Diff review used the existing
standard-library hash and state model, added no dependencies, comments or
suppressions, and preserved all existing checks.

## Full local check receipt

The full-check finding at 4e9fa02277e572b769e39f67395306e2ff28ffcd is
addressed with an executed full suite, not another selected-check claim:

    timeout 300 ~/.local/bin/heavy python3 -m unittest discover -s tests -t .

Result: exit 1, 287 tests, four failures in test_gatekeep_retry_limit. The
complete receipt is full-check.log. The independent required fast check
passes; see full-check-fast.log. No check or test was weakened or modified.

Failures: BackoffTest.test_a_second_retry_happens_after_the_backoff;
FirstRetryTest.test_a_head_with_no_retry_yet_is_retried;
FirstRetryTest.test_a_legacy_head_is_retried;
GiveUpTest.test_an_odd_record_does_not_stop_the_run.

Baseline isolation: git-show extracted coordinator/bin/coordq and
tests/test_gatekeep_retry_limit.py from base
8d6c70d4146cf857a59d0081159e784773837635 into a temporary directory with
matching paths. Both extracted files were asserted byte-identical to the
current checkout. Running `python3 -m unittest discover -s tests -p
test_gatekeep_retry_limit.py` there ran 14 tests and reproduced the same four
failures, exit 1; see full-check-baseline.log. This establishes an unchanged
baseline failure rather than a watcher regression. No changes to unrelated
coordq behavior or tests were made. The full suite result remains FAIL, not
waived or represented as PASS. The PR builder marker therefore reports FAIL
with the reason; the fast check is separately reported PASS.

Device, handset and live-service cases remain WAIVED, not failed. This turn
only adds receipts and documentation; watcher runtime and installer unchanged.

## Finish check correction

The earlier full-suite FAIL receipt remains historical evidence. The finish
fix moves the Astra identity guard into the quota fallback path, restoring
ordinary terminal-run retries while preserving quota routing restrictions,
retry limits and backoff. No tests or checks changed.

Validation on the resulting source tree:
- `timeout 300 python3 -m unittest tests.test_gatekeep_retry_limit`: PASS, 14 tests.
- `timeout 300 python3 -m unittest discover -s tests -t .`: PASS, 287 tests.
- `timeout 300 python3 scripts/mac_ops_fast_check.py`: PASS.

Receipts: finish-full-check.log and finish-fast-check.log. The heavy-wrapped
attempt was waiting in the queue; the direct full-suite command above completed.
One in-session read-only review found no blocking findings. Diff comment review
and bounded deslop inspection required no further changes.

## Left for later

Live watcher activation and authenticated service behavior remain unverified.
The coordinator owns the separate Opus gate.
