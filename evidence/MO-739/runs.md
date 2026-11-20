# MO-739 runs

Code commit: 875b13f23e6682cd0c240eedc0da27fdfde49ab3. No `--apply` was run on real worktrees.

## Dry run on this Mac, before and after

Command: `python3 cleaner.py --dry-run --no-report --state-root <scratch>`, with the origin/main cleaner (before) and this branch (after).

- Before: look 13, protected 30, safe 0, eligible 0.
- After: look 12, protected 36, safe 1, eligible 1.

Worktree that moves to removable because its PR merged:

- `~/.t3/worktrees/catalogue/t3-ctl-37-testflight-2-37cf3ae13057c687` (branch `t3/ctl-38-ipad-alt-icons`): before, protected; after, safe with no reasons. Its PR is merged and its HEAD is an ancestor of the PR head.

The two runs were minutes apart on a live machine, so other rows changed for live reasons (a PR opened, a thread ended). The openscan #29 and mac-ops #670 worktrees from the ticket were already gone from disk at run time, so they do not appear in either run.

An earlier version asked GitHub for each PR's `commits`, which GitHub rejects at `--limit 1000` (node limit), so 8 rows showed `github_pr_state_unavailable`. The final code asks only for `mergeCommit` and `headRefOid`, in the same single `gh pr list` call per branch as before, and the failures are gone.

## Fixture run (scratch repo under a temp dir, PR state stubbed)

Each worktree has a commit; the stubbed MERGED PR head is a later commit that contains the worktree's HEAD (not equal to it). Run with `apply=True`:

```
dirty look ['worktree_dirty'] exists=True
extra look ['github_pr_not_closed_for_head'] exists=True
merged removed [] exists=False
1 removed log lines
```

- merged: removed (folder gone, one "removed" log line, then `git worktree prune`).
- extra: same PR, plus one extra unpushed commit not in the PR head: kept (`github_pr_not_closed_for_head`).
- dirty: same PR, plus an untracked file: kept (`worktree_dirty`).

## Existing checks

See `check-proof.md` (`scripts/mac_ops_fast_check.py`). The repo has no separate cleaner test.
