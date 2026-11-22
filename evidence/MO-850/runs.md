# MO-850 runs

Gates, the gatekeep re-cut, the park re-cut and the unstick launch now send `{"type": "worktree"}`; `worktree_base` (coordq 349) fills `baseRef` `origin/main` and `startFromOrigin` true.

## Proof command

Before (origin/main, four root launches):

```
$ python3 -c "src=open('coordinator/bin/coordq').read()+open('coordinator/overnight/lane_driver.py').read(); assert '\"workspaceStrategy\": {\"type\": \"root\"}' not in src, 'root strategy still used'"
AssertionError: root strategy still used
```

After (this head): no output, exit 0.

## Launch args through worktree_base (sample PR, run from this worktree)

```
shyamsivakumar/mac-ops {'type': 'worktree', 'baseRef': 'origin/main', 'startFromOrigin': True} head in brief: True proof in brief: True close_check: False ff-main: False
shyamsivakumar/other-repo {'type': 'worktree', 'baseRef': 'origin/main', 'startFromOrigin': True} head in brief: True proof in brief: True close_check: True ff-main: True
recut {'type': 'worktree', 'baseRef': 'origin/main', 'startFromOrigin': True}
```

The gate brief still holds the head sha and the proof text. The mac-ops repo is a lane-merge repo, so its gate brief has no merge, close_check or fast-forward step. A reviewer-mode repo (other-repo above) keeps both steps in the brief.

## Reviewer-mode gate against a worktree

- `close_check.py` reads only through `gh` (no open() or local git), so it works from any directory that holds `coordinator/bin/close_check.py`. A worktree from `origin/main` of mac-ops holds it (checked in a throwaway worktree).
- The fast-forward step says to find the worktree with main checked out in `git worktree list`, or run `git fetch origin main:main` when none has it. `git worktree list` from a worktree lists the root checkout, so the step finds main the same way as before. The lane's own `fast_forward_main` (lane_driver 1636) runs `git -C <canonical>` and is untouched.
- Neither step needs the root checkout, so no call site stays on root.

## Real throwaway worktree

`git worktree add --detach <tmp> origin/main`, then `git fetch origin && git diff --stat origin/main~3...origin/main` printed `13 files changed, 492 insertions(+), 27 deletions(-)`. The worktree was removed with `git worktree remove`.

## What T3 does with the worktree

T3 worktrees live under `~/.t3/worktrees/<project>/` (268 entries there now): T3 does not remove a worktree when its thread ends. The daily tmp-sweep (04:30, per the storage-controls note) removes idle ones, so each gate leaves one disposable copy until the next sweep. Not verified: whether T3 0.1.10 detaches or names a branch (no real launch was made).
