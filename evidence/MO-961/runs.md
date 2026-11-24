# MO-961 runs (Refs #961)

## Ticket proof

Command: the ticket's proof, saved as a script and run from a repo root.

On origin/main (4375b7ab54, a temp copy from `git archive`):

```
AttributeError: module 'cq' has no attribute 'proof_changed'
main_exit=1
```

On the branch head: exit 0, no output.

## Named eval: close-evidence (coordinator/overnight/selftest.py)

Run alone through the selftest's own wrappers (live subprocess and process forbidden, fixture models).

- origin/main code with this branch's selftest: AssertionError at the first drive, `expected (1, [], 1, {'checks': 1, 'proof': 1}), got (1, [], 1, {'checks': 1, 'proof': 0})`: gatekeep never reached proof_gate for a PR without a receipt.
- branch: RESULT PASS.
- Mutation controls on a temp copy of the branch: with `uncard` made a no-op the eval fails (`[False, True, True]` instead of `[False, False, True]`); with the author check replaced by True it fails (a gate was queued for an untrusted ticket).

## Green-mode reruns of the last 8 mac-ops tickets

`proof_run.run("green", ~/Code/mac-ops, <merge commit>, <ticket command>)` in its temp checkout, one per ticket, with the real command from each ticket body. No gatekeep, no board, no journal.

| Ticket | PR | Merge commit | Command | State | Seconds |
| --- | --- | --- | --- | --- | --- |
| #958 | #959 | 4375b7ab54 | `HOME=$(mktemp -d) python3 -c "import importlib.machinery as ...` | green (exit 0) | 0.8 |
| #955 | #957 | 8774e10cef | `HOME=$(mktemp -d) python3 -c "import sys;sys.path.insert(0,'...` | green (exit 0) | 1.2 |
| #954 | #956 | 8cf0796f7d | `HOME=$(mktemp -d) python3 -c "import sys;sys.path.insert(0,'...` | green (exit 0) | 0.7 |
| #951 | #953 | ef7944b31d | `HOME=/nonexistent python3 -c "import os,sys,glob,tempfile,su...` | green (exit 0) | 0.7 |
| #950 | #952 | 223afc4853 | `HOME=$(mktemp -d) python3 -c "import importlib.machinery as ...` | green (exit 0) | 0.8 |
| #945 | #949 | cf5b343bdd | `python3 -c "import sys,subprocess,tempfile;sys.path.insert(0...` | green (exit 0) | 68.3 |
| #944 | #948 | a6eecb81b4 | `HOME=$(mktemp -d) python3 -c "import importlib.machinery as ...` | green (exit 0) | 1.1 |
| #943 | #947 | 898b247b85 | `HOME=$(mktemp -d) python3 -c "import importlib.machinery as ...` | green (exit 0) | 0.5 |

All 8 are green. #945 takes 68.3 s because its proof runs the installed selftest twice. A proof run by gatekeep is outside `heavy`, capped at 120 s by `proof_run`, and one per gatekeep run, so a slow proof like this holds one run for at most 120 s and every other head waits for the next run.

## Review round: head moved, missing sha, gated head text

- `run_head_proof` now reads FETCH_HEAD after the fetch; a head that is not the candidate's head is `fetch_failed` ("the pull request head moved to <sha>"), never that head's result. A `SystemExit` from `proof_run._resolve` (sha not in the checkout) is `fetch_failed` too, caught around that one call.
- close-evidence evals added: moved head (nothing run, one card after 3 tries); missing sha using the real `proof_run` code and a real temp git repo (a fresh copy of the `subprocess` module, since the selftest forbids live git); a gated head with a kept green proof returns the kept tail, with no run and no card.
- close-evidence: RESULT PASS on the branch.

## Live read-only run of proof_gate on PR #963 (head d27b5c53)

Real GitHub reads, real `proof_run`, temp COORDQ_DIR and COORD_JOURNAL_DIR (the one real `ticket_opened` row for #961 copied into the temp journal; it has no proofSha because it was opened before this change), `alarms.route_update` and `write_replay` stubbed. The live queue, board and journal were not touched.

| scopeIssue | State | Seconds |
| --- | --- | --- |
| 961 (the real ticket) | green (the ticket proof ran on the PR head) | 2.8 |
| 960 (a wrong ticket, no journal row) | legacy (nothing run, passes) | 0.5 |
