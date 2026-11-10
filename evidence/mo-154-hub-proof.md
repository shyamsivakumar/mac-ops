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
- `empryo/bin/emp-hub:1958` — `merge_record` builds the record from the
  evidence the gate already produced (`revision_inputs` for the pull request,
  head commit, checks state, review thread and verdict word; the gate for the
  review model and run).
- `empryo/bin/emp-hub:1966` — `write_merge_record` appends one line under the
  hub lock and logs a failed write instead of raising.
- `empryo/bin/emp-hub:2025` — `tool_thread_merge` now computes its result and
  then writes the record once, so a dry run, a refused merge and a real merge
  each write exactly one record. The merge rules, the revision logic and the
  returned payloads are unchanged.

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
- A record that cannot be written (the path is a directory) is logged and the
  merge still succeeds.

Full output: `evidence/mo-154-hub-proof.log`.

## Verification

- `python3 -u verification/check_hub_merge_evidence.py`: **3 tests OK**.
- `python3 -u verification/check_hub_turn_budget.py`: **7 tests OK** (existing
  hub proof, unchanged, including the merge-review provenance dry runs).
- `python3 -u verification/check_hub_single_instance.py`: **5 tests OK**
  (existing hub proof, unchanged).
- `python3 -m unittest discover -s tests -t .`: **51 tests OK**.
- `ast.parse` of `empryo/bin/emp-hub` and
  `verification/check_hub_merge_evidence.py`: exit 0.
- `python3 scripts/mac_ops_fast_check.py --plan`: selects the new proof for a
  syntax check and no `tests/` module (the hub is not a `.py` module).

## Deployment hold

No install, production drain, restart, cancellation, provider call or
installed-binary invocation. The installed `emp-hub` was never run with
arguments. Push and PR are requested, not deployment; the coordinator
installs. Rollback: revert the PR.
