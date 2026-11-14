# MO-254 plan and closeout

Goal: the board reports every open pull request with its next action, and the
shift dispatches that action once per head.

Implement the pull request state table in the existing board and action handlers.

1. Inspect classification, shift dispatch, queue dedupe and existing stub checks.
2. Extend the existing table and handlers with head-scoped actions and held/Ascend exclusions. Stop if an action requires a separate loop or file.
3. Run stub proofs, the live board read only, the full fast check and one reviewer round. Open a ready PR only after verification.

Pass criteria: every eligible stalled PR has one action, repeated shifts send once per head, changed heads can act again, and no unchecked head gates or shift merge occurs.

All live proof uses dry run. No secrets or ticket-side changes.

## History

The first attempt stopped at the explicit design boundary: `cmd_shift` only
read work items and wrote receipts, with no action dispatcher. The coordinator
then authorized the dispatcher inside `overnight shift` on resumption, with
coordq gate/fix and queue-backed thread sends, per-head keys, and no shift
merge, close or label operation.

## What landed

- `coordinator/overnight/overnight`: every open pull request gets a `state`
  (`draft`, `checks-unreadable`, `no-ticket-link`, `conflicts`,
  `check-failed`, `check-missing`, `check-passed-no-gate`, `gate-pass`,
  `gate-live`, `gate-queued`, `gate-ended-no-verdict`, `gate-unreadable`,
  `needs-you`) and the single `action` plus `actionCommand` that clears it.
  Drafts get `finish`, conflicts get `rebase`, a missing `Refs #n` gets
  `link`, a check that does not name the head gets `check`, a PASS gets
  `merge-fix`, a gate that ended without a verdict gets `regate`. The board
  JSON carries `states`, `noAction` and `oldestByState`, and the shift
  dispatches each selected command once through `coordq`.
- `coordinator/bin/coordq`: `pr-action` (`finish`, `link`, `check`, `rebase`,
  `regate`, `merge-fix`) with a head guard, a non-Ascend board check, a held
  ticket check, a builder thread lookup and a queue key of
  `action:repo#number:head`; `gate` and `fix` refuse when the pull request
  head moved since the board read; `check_names_head` reads the body line
  when the repository publishes no agent check.
- `coordinator/overnight/README.md`: the shift dispatches, and a dry run
  queues nothing.
- `tests/test_overnight_board.py`: state counting, oldest-by-state and
  dispatch coverage.

## Verification

- `tests/test_overnight_board.py`: 12 tests pass.
- Both scripts parse; `git diff --check` clean.
- Live read (`overnight board --json`, read only): 14 open pull requests,
  `noAction` 0, states `check-missing` 8, `gate-ended-no-verdict` 3,
  `gate-fail` 2, `needs-you` 1. Summary in `live-board.json`.
- `coordq pr-action ... --dry-run` proved the handler and the head guard
  without queueing anything.
- The repo fast check is reported in the pull request body. No live sends,
  push of main, merge or label change happened.
- One in-session cross-model reviewer round on the commit. Four of its five
  findings were fixed here: the `link` row was unreachable because the
  branch-key inference overwrote the linked issue, so the missing `Refs #n`
  check now reads the body reference; the fresh-gate append rechecks
  `regateHeads` under the final lock; `coordq` accepts the same check forms
  and the same ticket-reference line as the board. The fifth, a live gate
  carrying action `none` with state `gate-live`, is the intended shape: the
  state says the gate is running and there is nothing to dispatch.
- Re-read after those fixes: same 14 open pull requests, `noAction` 0, and
  `link` still reachable but unused, because no open pull request lacks a
  `Refs #n` line.

## Still missing, follow-up work

- Dedupe of already-sent fix heads: a fix is keyed by head, but a head that
  already received findings can still be re-sent when the gate and the tick
  both ask in one cycle; the send receipt needs to be read on the dispatch
  path, not only written.
- The re-gate path: `regate` can ask a dead gate thread once and can form a
  fresh gate from current evidence, but the retry after a second
  `ended-no-verdict` is untested and has no attempt cap.
- Held-ticket proofs: the held/Ascend refusal in `pr-action` is checked by
  reading labels, and no proof yet covers a held ticket, an Ascend repo, or a
  builder thread that disappears between the board read and the dispatch.
