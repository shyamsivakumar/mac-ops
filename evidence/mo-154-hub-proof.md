# MO-154 merge-gate evidence

Refs #72. Frozen base: `7be7ce3ac4725c2d135df91e06f690e5d7356113` (`main`).

## Behavior change

`emp_thread_merge` built the review verdict and the review model, returned them
to the caller and dropped them, so build traces had to read verdict lines out
of review threads. The hub now keeps its own record: every merge-gate
evaluation appends one JSON line to `~/.empryo-hub/merges.jsonl` with the
time, the task thread, the pull request number, the head commit, the checks
state, the review thread, the verdict word, the review model and run, whether
the merge happened and whether the call was a dry run. The record never holds
message text, and a write that fails is logged and the merge continues.

A refusal before the gate (a review thread, a live run) is not a merge-gate
evaluation and writes no record; every other outcome, including a refused
merge and a stale-revision refusal, writes exactly one record.

## Implementation

- `empryo/bin/emp-hub:10` — `MERGE_RECORD` names the append-only file.
- `empryo/bin/emp-hub:1959` — `merge_record` builds the record from the
  evidence the gate already produced (`revision_inputs` for the pull request,
  head commit, checks state, review thread and verdict word; the gate for the
  review model and run).
- `empryo/bin/emp-hub:1967` — `write_merge_record` appends one line under a
  dedicated lock (`MERGE_LOCK`, so a slow disk cannot block the hub's other
  work) and logs a failed write instead of raising.
- `empryo/bin/emp-hub:2026` — `tool_thread_merge` now computes its result and
  then writes the record, so a dry run, a refused merge and a real merge each
  write exactly one record. The merge rules, the revision logic and the
  returned payloads are unchanged. A merged pull request is recorded right
  after `gh pr merge` succeeds, before settle and cleanup, so a cleanup error
  cannot lose the record.

## Proof

`verification/check_hub_merge_evidence.py` (new) runs the hub from this
repository with `HOME` pointed at a temporary directory. Only GitHub I/O is
faked; no production store, socket, engine or pull request is touched.

- A dry run writes exactly one record: `verdictWord` `PASS`, `reviewModel`
  `subscriptions/gpt-6.1-terra` (the fallback model the review run reported),
  `reviewRunId`, `reviewThread`, `headSha`, `pullRequest`, `checksState`
  `green`, `merged` false, `dryRun` true. The record holds no message text.
- A real merge writes exactly one more record with `merged` true and `dryRun`
  false.
- A refused merge (`gh pr merge` fails) still writes one record with the gate
  it read.
- A failed review gate writes one record with the `FAIL` verdict word, the
  review model and the review run.
- A stale `expectedRevision` refusal writes one record with the gate it read
  now (the checks state that changed).
- A refusal before the gate (a review thread, a live run) writes no record.
- A record that cannot be written (the path is a directory) is logged and the
  merge still succeeds.

Full output: `evidence/mo-154-hub-proof.log`.

## Verification

- `python3 -u verification/check_hub_merge_evidence.py`: **7 tests OK**.
- `python3 -u verification/check_hub_turn_budget.py`: **7 tests OK** (existing
  hub proof, unchanged, including the merge-review provenance dry runs).
- `python3 -u verification/check_hub_single_instance.py`: **5 tests OK**
  (existing hub proof, unchanged).
- `python3 -m unittest discover -s tests -t .`: **51 tests OK**.
- `ast.parse` of `empryo/bin/emp-hub` and
  `verification/check_hub_merge_evidence.py`: exit 0.
- `python3 scripts/mac_ops_fast_check.py --plan`: selects the new proof for a
  syntax check and no `tests/` module (the hub is not a `.py` module).

## Review

One in-session Claude Opus review of commit `6ee6adf` (read-only, nothing
rerun by the reviewer): **VERDICT: PASS**. No critical or major findings; five
minor findings, all fixed in this branch before the PR. The fixes are
builder-verified (proof output above), not reviewer-verified:

- the record is written right after `gh pr merge` succeeds, before settle and
  cleanup, so a cleanup error cannot lose the record of a merged pull request
- the record file is written under a dedicated lock, so a slow disk cannot
  block the hub's other work
- the proof now covers a failed review gate, a stale-revision refusal and the
  two refusals that write no record
- the proof docstring no longer claims that only GitHub I/O is faked
- the proof now asserts that a failed write is logged

Open item: MO-152's collector does not read `merges.jsonl` yet. The ticket
allows a follow-up note in MO-152; the record fields are listed above and in
`docs/empryo-hub.md`.

## Deployment hold

No install, production drain, restart, cancellation, provider call or
installed-binary invocation. The installed `emp-hub` was never run with
arguments. Push and PR are requested, not deployment; the coordinator
installs. Rollback: revert the PR.
