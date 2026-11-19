# MO-673: coordq fills the worktree baseRef a hand-built launch leaves out

T3 0.1.10 refuses a `t3_thread_launch` whose `workspaceStrategy` is
`{"type": "worktree"}` with no `baseRef` ("Missing key at
workspaceStrategy.baseRef"). coordq retried three times and dropped the
item. Five launches were dropped this way since 2026-11-15, the latest
#11381 (SRW#1356 fix) at 13:36 on 2026-11-19.

`ticket start` and the lane already send `baseRef`
(`coordinator/bin/ticket:1278`). The dropped items were payloads callers
passed to `coordq start` by hand.

## What landed

- `coordinator/bin/coordq`: `worktree_base(tool, args)`, called from
  `call()` next to `with_model` and the `taskType` strip, so an item
  already in the queue gets the default when it is sent. When the tool is
  `t3_thread_launch` and the strategy is a `worktree` with no `baseRef`,
  it adds `baseRef: "origin/main"` and `startFromOrigin: true`. A caller's
  own `baseRef` and `startFromOrigin` are kept as given. A `root` or
  `existing_worktree` strategy, and every other tool, is left alone.
- `coordinator/overnight/selftest.py`: the `worktree-base-ref` eval, which
  loads `worktree_base` out of coordq by `ast` and `exec` (the same
  pattern `consolidation_guard` uses) and reads `DEFAULT_BASE_REF` from
  coordq's own constant, checked against the literal `origin/main`.
- `coordinator/bin/hourly_selftest.py`: the eval name added to `EXPECTED`.
- `evidence/MO-673/check-proof.md`: the check proof.

## Why the registry file is in the change

The suite's eval names are pinned in `EXPECTED` in
`coordinator/bin/hourly_selftest.py`, and the `watchdog` eval fails when
that list and the suite's own `EVALS` differ:

```python
exact(sorted(adapter.EXPECTED), sorted(EVALS))
```

So a new eval in `selftest.py` cannot land without its name in that file.
The ticket's scope section did not name it, and the close checklist read
the change as out of scope:

```
scope: fail - outside the ticket's stated scope: coordinator/bin/hourly_selftest.py
proof file: pass - evidence/MO-673/check-proof.md is present
checks: pass - every one of the 9 checks the proof file lists passed
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: FAIL shyamsivakumar/mac-ops#673
```

The ticket's scope section now names the file, with the reason. The
change itself is unchanged: the registry line is a mechanical consequence
of the eval the ticket asked for, not new work.

## The close checklist, after the scope correction

Read against the merged pull request #683 and the corrected ticket:

```
scope: pass - every changed file is inside the ticket's stated scope
proof file: pass - evidence/MO-673/check-proof.md is present
checks: pass - every one of the 9 checks the proof file lists passed
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: PASS shyamsivakumar/mac-ops#673
```

## Proof

The dispatch path itself, with `subprocess.run` stubbed to capture the
JSON that reaches `t3mcp`:

- `{"type": "worktree"}` → `{"type": "worktree", "baseRef": "origin/main", "startFromOrigin": true}`
- `{"type": "worktree", "baseRef": "origin/builder/x", "startFromOrigin": false}` → unchanged
- `{"type": "root"}` → unchanged
- `t3_thread_send` with a worktree strategy → unchanged

The eval also fails on a wrong default (`origin/wrong` →
`FAIL worktree-base-ref`) and on an in-place change to a pass-through
case, so it is not self-referential.

The passing run is `check-proof.md`.

## Left for later

Nothing.
