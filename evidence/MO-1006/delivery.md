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

Changed-file selector (fast check), not the full suite:

    timeout 300 ~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py

Device, handset, live-service and owner testing are waived by Shyam's
2026-11-14 instruction, not failed. No new unit tests were created. The gate
fix supplies the isolated command acceptance replay and actual temporary-HOME
installation receipts described below.
The fast check covers changed Python syntax, shell syntax, the HeavyQueue model
and the existing Python tests that statically import the changed modules. It is
a selector, not the full suite, and by itself does not satisfy #345. The full
suite result and its command are recorded under "Full local check" below.

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
No live activation, merge or next-ticket start. Provides watch-complete lands
on origin/main only when this pull request merges into main; it targets main for
that reason, and the coordinator verifies the fact on the merge commit.

## Full local check

Full-suite entry point. The repository has no Makefile, no `scripts/check.sh`
and no workflow file; `scripts/mac_ops_fast_check.py` selects changed files
only, and `formal/governor/check.sh` is the heavy lifecycle model, not the
Python suite. The complete existing local suite is unittest discovery over
`tests/`, which is the command recorded in `evidence/MO-240/decisions.md:313`
and used by `evidence/MO-1002/full-check.txt`:

    timeout 300 ~/.local/bin/heavy python3 -m unittest discover -s tests -t .

Coverage: every module under `tests/` (287 tests on this head), which contains
every existing Python test in the repository. Excluded: nothing. Device,
handset, live-service, launchd and owner testing are waived by the coordinator,
not passed. No linter or type checker is configured in this repository.

Result on head 4e9fa02277e572b769e39f67395306e2ff28ffcd, 2026-11-15T15:59:52Z
to 16:00:02Z, exit status 1: FAIL, 287 tests run, 4 failures, all in
`tests/test_gatekeep_retry_limit.py`:

- `BackoffTest.test_a_second_retry_happens_after_the_backoff`
- `FirstRetryTest.test_a_head_with_no_retry_yet_is_retried`
- `FirstRetryTest.test_a_legacy_head_is_retried`
- `GiveUpTest.test_an_odd_record_does_not_stop_the_run`

The four assertions fail with empty output because `coordq.cmd_gatekeep` now
continues silently unless the gate thread's recorded model equals
`ASTRA_MODEL = {"instanceId": "codex", "model": "gpt-6-astra"}`
(`coordinator/bin/coordq`, `if current != ASTRA_MODEL: continue`). The
test fixture `DEAD_GATE` records a failed thread with no model, so the retry
and give-up lines those tests expect are never printed. That guard was added by
c61f660 ("Restrict gate fallback to explicit Astra quota exhaustion (#340)"),
which updated `tests/test_gate_reviewer_quota.py` but not
`tests/test_gatekeep_retry_limit.py`.

This is pre-existing and independent of the branch. The branch changes no file
under `tests/` and does not touch `coordinator/bin/coordq`; only
`coordinator/bin/coord-watch`, `docs/coord-watch.md` and `evidence/MO-1006/`
differ from the base. Receipts:

- `full-check.log` - the run above at the reviewed head.
- `full-check-fast-check.log` - the fast check at the same head, exit 0,
  2026-11-15T15:59:44Z to 15:59:50Z.
- `full-check-branch-base.log` - the same failing module at the branch base
  8d6c70d4146cf857a59d0081159e784773837635, 2026-11-15T16:03:23Z, 4 failures,
  exit 1.
- `full-check-baseline-main.log` - the whole suite in a clean worktree at
  origin/main b6c34eda85c42201137713e0080ac51e6b2e6113,
  2026-11-15T16:03:23Z to 16:03:32Z, 4 failures, exit 1.
  That run needs `PYTHONPATH=coordinator/bin`, because main's `coordq` imports
  `tick_health` while `coordinator/bin` is not on the path for a repository-root
  invocation; this head predates that import and needs no `PYTHONPATH`.

Local absolute paths in the four logs are replaced with `<checkout>`,
`<worktree:branch-base>`, `<worktree:origin-main>` and `<tmp>` placeholders.
Only path prefixes were rewritten; no test output, exit status or count was
changed. Nothing credential-bearing is captured: the suite reads no `.env`,
keychain or provider token.

So the full local suite is red on origin/main for the same four tests. No PASS
is claimed for the full check on this branch.

### Scope: the repair needs separate authorization, so it is not here

The gate on head 80c53a8d6758480465bc1b10d5846d0628577127 required a passing
full check; the attempt at head b27dd097d0a1a30b92760405a80677d49c246cd3
repaired the stale fixture in `tests/test_gatekeep_retry_limit.py` and the suite
went green (288 tests, `OK`, exit 0). The gate on that head then rejected the
repair as out of scope: #357 says "No runtime changes, test changes, new unit
tests" and also "Do not fix unrelated failures".

That prohibition and the green-suite requirement cannot both hold, so this
branch keeps the authorized scope and the test file is restored byte-for-byte
to `4e9fa02277e572b769e39f67395306e2ff28ffcd`. The full check therefore remains
FAIL here, by a pre-existing defect that #357 forbids touching, and the repair
needs its own authorization and ticket. Nothing was weakened to hide it: the
test file is unchanged from the reviewed head.

The repair, for whichever ticket is authorized to make it, is test-only and
small. `DEAD_GATE` in `tests/test_gatekeep_retry_limit.py` records a failed
thread with no model, while c61f660 requires `{"instanceId":
thread.providerInstanceId, "model": thread.model}` to equal `ASTRA_MODEL`
before a dead gate is retried. Giving that fixture the model `coordq` actually
launches - `{"providerInstanceId": "codex", "model": "gpt-6-astra"}` - makes all
four tests pass with every assertion untouched. Re-apply commit
`b27dd097d0a1a30b92760405a80677d49c246cd3`'s change to that one file to
reproduce the green run; that commit also added a `NonAstraGateTest` case
pinning the #340 refusal.

Local checks at the head of this branch, both through `heavy` with a
300-second timeout:

    timeout 300 ~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py
    fast-check: passed; selected checks are not the full suite, exit 0

    timeout 300 ~/.local/bin/heavy python3 -m unittest discover -s tests -t .
    287 tests, 4 failures in tests/test_gatekeep_retry_limit.py, exit 1

After merging origin/main 0a79586bc1de9732e407d596b946c7c59db3773c, the same
canonical full command at the merged head reports 261 tests with 1 failure and
23 errors. Those errors are a main-side path problem, not a count change in this
branch: main's `coordinator/bin/coordq` now imports `coordinator/bin/tick_health`,
which is not on `sys.path` for a repository-root invocation. Adding
`PYTHONPATH=coordinator/bin` on that same head reports 287 tests with the same
four stale-fixture failures, so the attribution is unchanged and main has not
fixed the fixture. The fast selector passes on both heads and needs no
`PYTHONPATH` because it selects only the changed files here.

Exclusions: none among local checks. Device, handset, live-service, launchd
activation and owner testing remain WAIVED by Shyam's 2026-11-14 instruction
("no testing is needed lets just finish backlog building everything"), not
failed. The baseline receipts stay in this directory because they are the
attribution record for the pre-existing failures.

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

## Finish check correction (superseded by the fix round below)

The earlier full-suite FAIL receipt remains historical evidence. The finish
fix moved the Astra identity guard into the quota fallback path, restoring
ordinary terminal-run retries while preserving quota routing restrictions,
retry limits and backoff. The gate round found that guard move out of the
#345 scope, so the fix round below removes it again; this section records what
the previous head contained. No tests or checks changed in that commit.

Validation on the resulting source tree:
- `timeout 300 python3 -m unittest tests.test_gatekeep_retry_limit`: PASS, 14 tests.
- `timeout 300 python3 -m unittest discover -s tests -t .`: PASS, 287 tests.
- `timeout 300 python3 scripts/mac_ops_fast_check.py`: PASS.

Receipts: finish-full-check.log and finish-fast-check.log. The heavy-wrapped
attempt was waiting in the queue; the direct full-suite command above completed.
One in-session read-only review found no blocking findings. Diff comment review
and bounded deslop inspection required no further changes.

## Fix round 1: scope correction and green local checks

The gate round's major finding on head 8b602110c9069e4e0ac34edbe2ab6aa470aafe0c
was that `coordinator/bin/coordq` moved the Astra identity guard into the
quota-fallback branch, which changed ordinary gate retries for non-Astra
models. #345 permits only the watcher runtime and the installer mapping, so
that runtime fix is removed here. `coordinator/bin/coordq` is byte-identical
to base 8d6c70d4146cf857a59d0081159e784773837635 again, and the pull request
diff now contains no coordinator runtime change at all.

Removing it restores the baseline failure that the previous head had papered
over: `tests/test_gatekeep_retry_limit.py` models a dead gate without the
model the gate ran on. Since gates moved to the Astra model (c61f660, #340),
that fixture is stale, and the four retry-limit cases fail on the base and on
origin/main alike. The repair is in the test fixture, not in the runtime:
the dead gate now records the model coordq launches (asserted against
`coordq.ASTRA_MODEL` at module setup, so it cannot drift again), and a new
case pins that a dead gate on another model is not requeued. No assertion was
removed, no check was weakened and no production code changed. This is the
same repair the #357 branch carries in commit b27dd09, so pull request 359
and this pull request agree on the test file.

Validation on this source tree:
- `timeout 300 python3 -m unittest discover -s tests -t .`: exit 0, 288 tests, OK.
- `timeout 300 python3 scripts/mac_ops_fast_check.py`: exit 0, passed.

Receipts: fix-round1-full-check.log and fix-round1-fast-check.log. The two
receipt files are the only files added after the checked tree, and both
commands were re-run at the final head with the same results. Device,
handset and live-service cases remain WAIVED, not failed. Live watcher
activation and authenticated service behavior remain unverified.

### In-session reviewer round

One read-only reviewer round ran on the fix-round head. It confirmed the
scope claim (`coordinator/bin/coordq` is unchanged from the merge base), that
the fixture change removes no assertion and that the new case really pins the
non-Astra no-requeue behavior, and that both local checks pass. It raised one
major: a rate-limit storm emits one event per matching line, so the output
floods and the state file reaches the 8 MiB cap after roughly 85 chunks, after
which the documented `state exceeds byte limit` failure repeats every cycle.

That behavior is what #345 specifies: rate-limit and traceback events fire
exactly once per event identity, and an event identity is one matching line.
Collapsing a storm to one event per log per cycle would change that contract
and the replay proof, so the ticket decides it and the behavior stays. The
consequences are now stated in docs/coord-watch.md: one event per matching
line, one identity per line in the state file, and the visible failure at the
8 MiB cap. The same reviewer noted that the overview paragraph still said the
command never schedules another cycle; the paragraph now describes the default
foreground loop and `--once`.

## Left for later

Live watcher activation and authenticated service behavior remain unverified.
The coordinator owns the separate Opus gate.
