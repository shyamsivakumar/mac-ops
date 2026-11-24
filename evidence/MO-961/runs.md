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

All 8 are green. #945 takes 68.3 s (cause not investigated); that is inside the 120 s limit but over half of it. Nothing was hidden or retried.
