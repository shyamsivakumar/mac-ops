# MO-639 paper replays

Three failing gate reports, read from the gate threads, each major re-classified under the new severity bar (gate_bar.py "Severity bar" and the round 2 rule). Paper replay only: no reviewer was rerun.

| PR | Finding | Old verdict | New class | New verdict |
| --- | --- | --- | --- | --- |
| #623 | `coordq:153`, a backtick fence inside a tilde fence flips `has_verdict` | major | minor | PASS |
| #627 | `bot1_rollback_dry_run.py:104`, tied timestamps on two `REMOVED` records at the same commit | major | minor | PASS |
| #625 | `lane_driver.py:590`, unblocked send can take a fresh worktree when another request holds the reservation | major | major | FAIL |
| #625 | `lane_driver.py:516`, reservation holder found by title substring over at most 5 matches | major | major | FAIL |
| #625 | `lane_driver.py:586`, blocked running thread with local-only work restarts from `origin/main` | major | major | FAIL |
| #625 | `test_lane_duplicate_suppression.py:201`, 190 changed lines against a limit of about 150 | minor | minor | (listed) |

## #623 (thread mcp:launch:c16c528c...), PASS under the new bar

The reviewer's own cases need a gate report that has a tilde fence holding a backtick fence holding a verdict line. Our gate reports end on `CHECK:` and `VERDICT:` lines and quote code in single-level fences, so the input is one our own tools do not produce. The wrong result is also cheap: one extra queued gate or one skipped retry. No data loss, no bad merge, no stuck lane. The new bar calls it minor. It goes under "Left for later" and the PR passes, which would have saved the three rounds that ended in the re-cut #636.

## #627 (thread mcp:launch:cea6aae8...), PASS under the new bar

The case needs two deployments with the same timestamp to the millisecond at the same commit, and the script is a read-only dry run. The failure is a refusal (exit 1, no command printed), so no rollback happens at all and nothing is harmed. The reviewer's sentence for how often it happens would be "rarely, if Vercel ever stamps two records identically". That fails "likely in real use" and "hard to undo". Minor, PASS. The reviewer also noted the 206 lines against a limit of about 150 and the missing live output; both were already minor.

## #625 (thread mcp:launch:4781d9fe...), still FAIL, honestly

Three majors survive, with different confidence:

- `lane_driver.py:516` (title-substring holder, five-match cap) is the strongest. The trigger is five completed threads with a matching title, which retries and fix rounds on one ticket produce routinely. The result is two agents in one worktree, which overwrites work and is hard to undo. Stays major.
- `lane_driver.py:586` (blocked thread with local-only work restarts from `origin/main`). Model blocks mid-build are the case the PR exists for, and an unpushed local branch is common before the first PR. The new thread gets the message without the work. The old work is not destroyed, so this is the weakest on "hard to undo", but it is likely, so it stays major.
- `lane_driver.py:590` (unblocked send takes a fresh worktree) is the most borderline. It needs a second request to hold the reservation at the same time, and reservations are new in this PR. It stays major because it changes the common unblocked path that the ticket says must not change, and the PR's own replay expects the changed result. Under the new bar the reviewer would have to write one sentence on how often two requests target one checkout; if the honest answer is "rarely", it drops to minor.

The new bar does not rescue #625. It would also have limited later rounds to changed lines plus these three open majors.
