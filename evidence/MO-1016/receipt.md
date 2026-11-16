# MO-1016 receipt: complete local checks for the preserved watcher

Refs #366, Refs #357, Refs #345, Refs #359.

Run ticket: ticket:shyamsivakumar/mac-ops#366:a1. Chain 2 of 2.

## What was already true on origin/main

The preserved watcher implementation is `coordinator/bin/coord-watch`
(661e2c8, "Add coord-watch runtime alarms and foreground loop (#352)") with
the installer mapping owned by `install_coordinator.plan`, which installs
every file under `coordinator/bin` and so maps `coord-watch` to
`~/.local/bin/coord-watch` at mode 0755.

Both blockers named by the ticket are on origin/main:

- coordq root import: e7b66a4 (#364, PR #422) inserts the `coordq` sibling
  directory on `sys.path`, so `from tick_health import tick_alarm` resolves
  when `coordq` is loaded by path.
- retry fixture current: 661e2c8 (#352) repaired the stale `DEAD_GATE`
  fixture in `tests/test_gatekeep_retry_limit.py` and pinned the non-Astra
  no-requeue case. No assertion was removed. That commit is the last change
  to that test file on origin/main; f0236b1 (#357, PR #359) changed only
  evidence files and left the test blob untouched.

The gate policy is unchanged: the complete local suite is
`python3 -m unittest discover -s tests -t .`, run from the repository root
with no `PYTHONPATH` workaround.

## The one blocker found on this head

`evidence/MO-1006/replay.py` failed before it reached the installation
cases:

    require("coord-watch" in installer.BIN_FILES, "missing BIN_FILES mapping")
    AttributeError: module 'installer' has no attribute 'BIN_FILES'

`install_coordinator.py` has no `BIN_FILES` constant; the installer maps
`coordinator/bin` wholesale. The #359 rebase reverted that repair
(529c09b restored the old assertion and dropped the inert
`require_real_home` / `require_healthy` host guards), so the isolated replay
aborted at the mapping step and the temporary-HOME installation proof never
ran on the merged head.

Repair: restore the mapping assertion against `installer.plan()` and the two
inert host guards, exactly as c982cc9 had it. This is an evidence script
change only. No runtime file, no unit test and no check is changed, weakened
or skipped.

## Check results at head 688bc05fafaef40a0c5e60744490b48b33c25c21

Commands, exits and logs, all from the repository root with a 300 second
timeout. The full suite and the fast check run through `~/.local/bin/heavy`;
the replay runs `python3` directly, as the ticket command specifies:

| Check | Command | Exit | Receipt |
| --- | --- | --- | --- |
| Full suite | `timeout 300 ~/.local/bin/heavy python3 -m unittest discover -s tests -t .` | 0 | `full-check.log` |
| Fast check | `timeout 300 ~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py` | 0 | `fast-check.log` |
| Isolated replay | `timeout 300 env PYTHONDONTWRITEBYTECODE=1 python3 evidence/MO-1006/replay.py` | 0 | `replay.out` |

Full suite: 288 tests, `OK`, exit 0. No `PYTHONPATH` was set and none is
needed at this head.

Fast check: `fast-check: passed; selected checks are not the full suite`,
exit 0. It is a changed-file selector, not the suite.

Isolated replay: exit 0, all 29 acceptance cases PASS. That includes the
actual command replay, the temporary-HOME installation with the inert host
guards and the forbidden-subprocess boundary, the persisted-generation dedup
cases (identical-line copy truncation, anchor-detected truncate and regrow,
truncation restart dedup) and the write-boundary and private-marker checks.
The replay reads only synthetic sources and a temporary HOME. No live
installation, no launchd activation and no production process was started.

These committed receipts were produced at 688bc05, the commit that added
them. Every later commit changes HEAD, so the final logs are rerun at the
final head and attached to the pull request body externally. The pull
request body carries the final SHA and the final log tails; the committed
logs name the earlier head they were run at.

## Historical Builder check correction

PR #359's body carries `Builder check: PASS 529c09b17d5459f6a356f697359ba1654d22380b`.
That marker covered only the fast check at that head; the same body says the
complete suite was queued and stopped before admission and that no
full-suite PASS is claimed. Read literally, the marker line reads as a
complete-suite PASS. It is not one.

This pull request states the complete local check at the head it names:

    Builder check: PASS <full sha of this head>

and the full-suite command, exit and log are recorded above and in the pull
request body. Historical receipts apply only to their named heads.

## Waived, not passed

Device, handset, live-service, launchd activation and owner testing are
waived by Shyam's 2026-11-14 instruction. They are not passed and not
failed. Live watcher activation and authenticated service behavior remain
unproved.
