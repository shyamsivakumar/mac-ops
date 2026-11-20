# MO-514 part 1 runs

Read-only runs of `scripts/worktree-cleaner/cleaner.py --dry-run --no-report` on the real worktrees, with a scratch `--state-root`. Nothing was removed.

| Run | safe | needs a look | protected | prune |
| --- | --- | --- | --- | --- |
| before (origin/main 23c0bebf) | 36 | 13 | 27 | 0 |
| after (this change) | 36 | 13 | 27 | 0 |

No worktree moved. A scan of every worktree under `~/.t3/worktrees`, `~/Code/.worktrees` and `~/Code/*/.claude/worktrees` found no `.specstory/` or `.agents/legacy-instructions.md` entry, so none of the 13 "needs a look" worktrees is held only by bootstrap files.

Fixture run of `status_for` on a scratch repo outside the repository:

| State | Result |
| --- | --- |
| untracked `.specstory/h.md` and `.agents/legacy-instructions.md` only | clean |
| the same plus untracked `real.txt` | dirty, only `?? real.txt` listed |
| the same plus untracked ` .specstory-x` (leading space, lookalike name) | dirty, listed |

`python3 scripts/mac_ops_fast_check.py --proof evidence/MO-514/check-proof.md` through `heavy`: passed. The repo has no cleaner tests, so the check does not exercise the cleaner beyond a syntax compile.
