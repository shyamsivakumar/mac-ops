Summary: MO-149 passes this final round, with no critical or major findings and two minor proof-log notes. The lock, usage-only argument handling and provider-limit removal match the task, and the `turnLimits` setting is kept. I only read the diff and the logs; no command or proof was rerun.

**Production (`empryo/bin/emp-hub`, `empryo/hub/routing.json`)**
- **Lock order:** `prepare_startup` (`emp-hub:74-91`) runs before the `Store` class is defined at line 94. Lines 1-50 only define constants, so nothing reads stores or touches the socket before the lock.
- **Lock file:** it is never unlinked. Python does not pass the descriptor to child engines by default, so engines cannot hold the lock.
- **Arguments:** any argument prints usage and exits 0 before `makedirs`.
- **Provider limits:** `SLOTS`, `limit_of`, `acquire_slot`, `release_slot`, the status `limits` field and the routing `limits` block are all gone. A grep of `empryo/` finds no remaining callers.
- **Cleanup order:** `finish_run` still runs `settle_breaker` and then `release_engine` in nested `finally` blocks. `turnLimits` is unchanged.
- **Module guard:** `if __name__ == "__main__"` is a normal guard, not a shim.

**Proof edits (`verification/check_hub_turn_budget.py`)**
- Every diff hunk falls inside the approved ranges: line 7, 23-30, 103-107, 126, 198-232 and 351-386. Nothing outside them changed.
- The prepared PR body quotes the approval and has a zero-context diff of every changed line. That diff matches the actual diff.
- The resume run/record counts and the full persisted-record equality check are kept. The new drain-queue test covers the zero-clock case that the removed queue checks used to cover.

**Other files**
- `verification/check_hub_single_instance.py` is new on this branch. Its 5 tests cover second-start rejection, the lock coming before store reads, `--help` with no state touched, a live socket kept, and the lock being freed on exit.
- `docs/empryo-hub.md` cites `empryo/bin/empq:96-98`; those lines are the `n >= cap()` check.

**Proof (builder output, read only)**
- `evidence/mo-149-canonical-wall-clock.log` shows the `SECOND HUB` banner, both turns cancelled with "turn ran over 10 min", both runs recorded as failed, and `WALL CLOCK PASS`.
- `evidence/mo-149-followup-proof.log` shows startup 5 OK, canonical 7 OK, repo 51 OK and py_compile exit 0.

Findings:
- minor | evidence/mo-149-canonical-wall-clock.log:1-7 | The log has no command line, exit code or elapsed time. The "exit 0, 10m 1s" figures appear only in the follow-up note and the PR body, so I could not confirm them from the log. | Add the command, `exit=0` and the duration to the log before publishing.
- minor | evidence/mo-149-canonical-wall-clock.log:5 | Two log lines from the concurrent runs are merged onto one line. This is cosmetic. | Leave it, or add a note.
- minor | (untracked) evidence/*, verification/check_hub_single_instance.py | These files are untracked. The commit must include them, or the PR's proof references will break. | Stage all evidence files and the new check when committing.

Deployment (install or restart) is still not authorized.

VERDICT: PASS

Files examined: /Users/shyamsivakumar/.local/share/empryo/tee/2026-11-10T22-24-34-825Z_shell_b6396fed.txt, /Users/shyamsivakumar/.empryo-hub/worktrees/mac-ops/mo-149-hub-single-instance-guard-install-mo-147--2a749f/evidence/mo-149-followup.md, /Users/shyamsivakumar/.empryo-hub/worktrees/mac-ops/mo-149-hub-single-instance-guard-install-mo-147--2a749f/.empryo/tmp/tabs/dfc4cb65-c80d-4bad-aa6e-e0244506fbdc/mo-149-pr.md, /Users/shyamsivakumar/.empryo-hub/worktrees/mac-ops/mo-149-hub-single-instance-guard-install-mo-147--2a749f/verification/check_hub_single_instance.py, /Users/shyamsivakumar/.empryo-hub/worktrees/mac-ops/mo-149-hub-single-instance-guard-install-mo-147--2a749f/evidence/mo-149-canonical-wall-clock.log, /Users/shyamsivakumar/.empryo-hub/worktrees/mac-ops/mo-149-hub-single-instance-guard-install-mo-147--2a749f/empryo/bin/emp-hub, /Users/shyamsivakumar/.empryo-hub/worktrees/mac-ops/mo-149-hub-single-instance-guard-install-mo-147--2a749f/empryo/bin/empq