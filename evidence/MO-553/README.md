# MO-553: a Ruff gate with a baseline

Step 1 of the gradual typing plan (Coder, approved by Shyam 2026-11-18).
The check proved only that changed files parse, so a typo in a rare safety path
passed. The check now runs Ruff as well, and fails only on findings the
baseline does not have.

## What landed

- `scripts/mac_ops_fast_check.py`: one new step, `ruff F,B`, run through
  `uvx ruff@0.14.0`. The version is pinned, so the check never installs an
  unpinned tool. There is still one check runner.
- `scripts/ruff-baseline.txt`: the findings Ruff reports today, one line per
  finding with its count. The check fails on a finding the baseline does not
  have, and passes on a finding it does.
- `README.md`: the check section says what the Ruff step does and how to
  regenerate the baseline.
- `tests/test_check_proof.py`: tests for the baseline comparison, the pinned
  command, the baseline file round trip, the gate itself (a finding outside
  the baseline fails it, a known finding passes it), the runners without a
  `.py` suffix, and a missing tool recorded as `not run`.

## The baseline, as counted today

Ruff 0.14.0, rule sets F and B, over the whole repository and the three
runners without a `.py` suffix (`coordinator/overnight/overnight`,
`coordinator/bin/coord-watch`, `coordinator/pi/bin/coord-tick`):

| Rule | Findings |
| --- | --- |
| B023 | 54 |
| F401 | 11 |
| F841 | 8 |
| B904 | 6 |
| F541 | 3 |
| B905 | 3 |
| B020 | 1 |
| Total | 86 |

86 findings in 53 distinct entries, over 20 files. The baseline file holds one
line per distinct entry with its count, the fields separated by a tab, so a
path or a message with a space in it still round trips:

```
1	coordinator/overnight/lane_driver.py	F841	Local variable `key` is assigned to but never used
9	coordinator/overnight/selftest.py	B023	Function definition does not bind loop variable `actions`
```

The counts are per finding, not per line number, so a file that grows or moves
does not fall out of the baseline.

## Proof

The passing run: `check-proof.md`. The Ruff row reads
`passed | 86 findings, all in the baseline`.

### A deliberate typo fails the check

A copy of `coordinator/bin/proof_file.py` was put at
`evidence/MO-553/scratch/proof_file_copy.py` with an unused variable appended:

```python
def scratch_typo():
    unused_variable = 1
    return 2
```

`python3 scripts/mac_ops_fast_check.py --proof evidence/MO-553/demo-ruff-typo.md`
exited 1, and the proof file records:

```
| ruff F,B | `uvx ruff@0.14.0 check --select F,B --output-format json . coordinator/overnight/overnight coordinator/bin/coord-watch coordinator/pi/bin/coord-tick` | failed | 1 Ruff findings are not in the baseline; first: evidence/MO-553/scratch/proof_file_copy.py F841 Local variable `unused_variable` is assigned to but never used |
```

The scratch copy was deleted after the run; it is not in the change.

### Without uvx the check says not run

`env PATH=/usr/bin:/bin python3 scripts/mac_ops_fast_check.py --proof
evidence/MO-553/demo-ruff-no-uvx.md` exited 1 with `fast-check: incomplete`,
and the proof file records:

```
| ruff F,B | `uvx ruff@0.14.0 check --select F,B --output-format json . ...` | not run | uvx is not installed |
```

The run is not a pass for Ruff, and the proof file says so: the proof file
carries `Run result: incomplete`, and the run exits 1. A lint that never ran
must not read as a clean check.

## Left for later

- Step 2: mypy, one module at a time, starting with `board_resources.py`.
- Step 3: pin all the check tools through `uvx`.
- The 86 findings in the baseline are not fixed here; they are recorded, so the
  gate can land before the cleanup.
